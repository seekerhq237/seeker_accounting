from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.purchases.dto.purchase_bill_dto import PurchaseBillListItemDTO
from seeker_accounting.modules.purchases.ui.purchase_bill_dialog import PurchaseBillDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver
from seeker_accounting.shared.ui.guided_resolution_coordinator import GuidedResolutionCoordinator
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.pager import Pager
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.register import RegisterPage
from seeker_accounting.shared.ui.table_helpers import configure_dense_table
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


class PurchaseBillsPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._bills: list[PurchaseBillListItemDTO] = []
        self._total_count: int = 0
        self._pending_resume_payload: ResumeTokenPayload | None = None
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(lambda: self.reload_bills(reset_page=True))

        self.setObjectName("PurchaseBillsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        self._populate_action_band(self._register)
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_bills()

    def reload_bills(
        self,
        selected_bill_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._bills = []
            self._total_count = 0
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._pager.reset()
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        if reset_page:
            self._pager.reset()

        search_text = self._search_input.text().strip() or None
        try:
            page_result = self._service_registry.purchase_bill_service.list_purchase_bills_page(
                active_company.company_id,
                status_code=self._status_filter_value(),
                query=search_text,
                page=self._pager.page,
                page_size=self._pager.page_size,
            )
        except Exception as exc:
            self._bills = []
            self._total_count = 0
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._pager.reset()
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Purchase Bills", f"Bill data could not be loaded.\n\n{exc}")
            return

        self._bills = list(page_result.items)
        self._total_count = page_result.total_count
        self._pager.apply_result(page_result)
        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_bill_id)
        self._update_action_state()

    def _handle_search_text_changed(self, _text: str) -> None:
        self._search_debounce.start()

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._search_input = QLineEdit(register.toolbar_strip)
        self._search_input.setPlaceholderText("Search bills…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        strip_layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Posted", "posted")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_bills(reset_page=True))
        strip_layout.addWidget(self._status_filter_combo)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_bills())
        strip_layout.addWidget(self._refresh_button)

    def _populate_action_band(self, register: RegisterPage) -> None:
        band_layout = register.action_band_layout

        self._new_button = QPushButton("New Bill", register.action_band)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        band_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", register.action_band)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        band_layout.addWidget(self._edit_button)

        self._cancel_button = QPushButton("Cancel Draft", register.action_band)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_draft)
        band_layout.addWidget(self._cancel_button)

        self._post_button = QPushButton("Post Bill", register.action_band)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_bill)
        band_layout.addWidget(self._post_button)

        band_layout.addStretch(1)

        self._print_button = QPushButton("Print / Export", register.action_band)
        self._print_button.setProperty("variant", "ghost")
        self._print_button.clicked.connect(self._print_selected_bill)
        band_layout.addWidget(self._print_button)

        self._export_list_button = QPushButton("Export List", register.action_band)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._print_bill_list)
        band_layout.addWidget(self._export_list_button)

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._table_surface = self._build_table_surface()
        self._empty_state = self._build_empty_state()
        self._no_active_company_state = self._build_no_active_company_state()
        self._stack.addWidget(self._table_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_active_company_state)
        return self._stack

    def _build_table_surface(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._table = QTableWidget(container)
        self._table.setObjectName("PurchaseBillsTable")
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels((
            "Bill #",
            "Date",
            "Due Date",
            "Supplier",
            "Total",
            "Open Balance",
            "Payment",
            "Status",
            "Posted At",
        ))
        configure_dense_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._table, 1)

        self._pager = Pager(container, default_page_size=100)
        self._pager.page_changed.connect(lambda _p: self.reload_bills())
        self._pager.page_size_changed.connect(lambda _s: self.reload_bills(reset_page=True))
        layout.addWidget(self._pager)
        return container

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No purchase bills yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first draft purchase bill, add line items with expense accounts and tax codes, "
            "then post when the bill is complete.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Bill", actions)
        create_button.setProperty("variant", "primary")
        create_button.clicked.connect(self._open_create_dialog)
        actions_layout.addWidget(create_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    def _build_no_active_company_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("Select an active company first", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Purchase bills are company-scoped. Choose the active company before creating or posting bills.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        companies_button = QPushButton("Open Companies", actions)
        companies_button.setProperty("variant", "secondary")
        companies_button.clicked.connect(self._open_companies_workspace)
        actions_layout.addWidget(companies_button, 0, Qt.AlignmentFlag.AlignLeft)
        actions_layout.addStretch(1)

        layout.addWidget(actions)
        layout.addStretch(1)
        return card

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _status_filter_value(self) -> str | None:
        value = self._status_filter_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
        elif len(self._bills) == 0:
            self._stack.setCurrentWidget(self._empty_state)
        else:
            self._stack.setCurrentWidget(self._table_surface)

    def _populate_table(self) -> None:
        self._table.setUpdatesEnabled(False)
        self._table.setSortingEnabled(False)
        try:
            self._table.setRowCount(len(self._bills))
            for row, bill in enumerate(self._bills):
                number_item = QTableWidgetItem(bill.bill_number)
                number_item.setData(Qt.ItemDataRole.UserRole, bill.id)
                self._table.setItem(row, 0, number_item)
                self._table.setItem(row, 1, QTableWidgetItem(str(bill.bill_date)))
                self._table.setItem(row, 2, QTableWidgetItem(str(bill.due_date)))
                self._table.setItem(row, 3, QTableWidgetItem(bill.supplier_name))
                total_item = QTableWidgetItem(f"{bill.total_amount:.2f}")
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row, 4, total_item)
                balance_item = QTableWidgetItem(f"{bill.open_balance_amount:.2f}")
                balance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row, 5, balance_item)
                self._table.setItem(row, 6, QTableWidgetItem(bill.payment_status_code.title()))
                self._table.setItem(row, 7, QTableWidgetItem(bill.status_code.title()))
                posted = bill.posted_at.strftime("%Y-%m-%d %H:%M") if bill.posted_at else ""
                self._table.setItem(row, 8, QTableWidgetItem(posted))
        finally:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)

        search_text = self._search_input.text().strip()
        total = self._total_count
        shown = len(self._bills)
        if search_text:
            self._record_count_label.setText(f"{shown} shown of {total} matches")
        else:
            self._record_count_label.setText(
                f"{total} bill" if total == 1 else f"{total} bills"
            )

    def _apply_search_filter(self) -> None:
        # Search is now handled server-side via reload_bills. Kept as a
        # no-op for backward compatibility with any external callers.
        return

    def _restore_selection(self, bill_id: int | None) -> None:
        if bill_id is None or self._table.rowCount() == 0:
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == bill_id:
                self._table.selectRow(row)
                return
                return

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Purchase Bills",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        selected = self._table.currentRow() >= 0
        has_company = self._active_company() is not None
        selected_bill = self._bills[self._table.currentRow()] if selected else None
        is_draft = selected_bill and selected_bill.status_code == "draft"
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_company and permission_service.has_permission("purchases.bills.create")
        )
        self._edit_button.setEnabled(
            selected and is_draft and permission_service.has_permission("purchases.bills.edit")
        )
        self._cancel_button.setEnabled(
            selected and is_draft and permission_service.has_permission("purchases.bills.cancel")
        )
        self._post_button.setEnabled(
            selected and is_draft and permission_service.has_permission("purchases.bills.post")
        )
        self._print_button.setEnabled(has_company and selected)
        self._export_list_button.setEnabled(has_company and bool(self._bills))
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self):
        return {
            "purchase_bills.new": self._open_create_dialog,
            "purchase_bills.edit": self._open_edit_dialog,
            "purchase_bills.cancel": self._cancel_selected_draft,
            "purchase_bills.post": self._post_selected_bill,
            "purchase_bills.refresh": self.reload_bills,
            "purchase_bills.print": self._print_selected_bill,
            "purchase_bills.export_list": self._print_bill_list,
        }

    def ribbon_state(self):
        return {
            "purchase_bills.new": self._new_button.isEnabled(),
            "purchase_bills.edit": self._edit_button.isEnabled(),
            "purchase_bills.cancel": self._cancel_button.isEnabled(),
            "purchase_bills.post": self._post_button.isEnabled(),
            "purchase_bills.refresh": True,
            "purchase_bills.print": self._print_button.isEnabled(),
            "purchase_bills.export_list": self._export_list_button.isEnabled(),
        }

    def _handle_active_company_changed(self) -> None:
        self.reload_bills()

    def _handle_item_double_clicked(self, _item) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._bills):
            return
        bill = self._bills[row]
        self._service_registry.navigation_service.navigate(
            nav_ids.PURCHASE_BILL_DETAIL,
            context={"bill_id": bill.id},
        )

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.bills.create"):
            self._show_permission_denied("purchases.bills.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_error(self, "Create Bill", "Select an active company first.")
            return
        if not run_document_sequence_preflight(
            self, self._service_registry,
            active_company.company_id, active_company.company_name,
            "purchase_bill", nav_ids.PURCHASE_BILLS,
        ):
            return

        result = PurchaseBillDialog.create_bill(
            self._service_registry,
            active_company.company_id,
            active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_bills(result.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.bills.edit"):
            self._show_permission_denied("purchases.bills.edit")
            return
        if self._table.currentRow() < 0:
            return
        bill = self._bills[self._table.currentRow()]
        active_company = self._active_company()
        if active_company is None:
            return

        result = PurchaseBillDialog.edit_bill(
            self._service_registry,
            active_company.company_id,
            active_company.company_name,
            bill.id,
            parent=self,
        )
        if result is not None:
            self.reload_bills(result.id)

    def _cancel_selected_draft(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.bills.cancel"):
            self._show_permission_denied("purchases.bills.cancel")
            return
        if self._table.currentRow() < 0:
            return
        bill = self._bills[self._table.currentRow()]
        if bill.status_code != "draft":
            show_error(self, "Cancel Bill", "Only draft bills can be cancelled.")
            return

        reply = QMessageBox.question(
            self,
            "Cancel Draft Bill",
            f"Cancel draft bill {bill.bill_number}? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            active_company = self._active_company()
            if active_company is None:
                return
            self._service_registry.purchase_bill_service.cancel_draft_bill(
                active_company.company_id,
                bill.id,
            )
            self.reload_bills()
            show_info(self, "Bill Cancelled", f"Bill {bill.bill_number} cancelled successfully.")
        except Exception as exc:
            show_error(self, "Cancel Bill", f"Could not cancel bill.\n\n{exc}")

    def _post_selected_bill(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.bills.post"):
            self._show_permission_denied("purchases.bills.post")
            return
        if self._table.currentRow() < 0:
            return
        bill = self._bills[self._table.currentRow()]
        if bill.status_code != "draft":
            show_error(self, "Post Bill", "Only draft bills can be posted.")
            return

        reply = QMessageBox.question(
            self,
            "Post Purchase Bill",
            f"Post bill {bill.bill_number}? This creates a journal entry and locks the bill.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        active_company = self._active_company()
        if active_company is None:
            return
        try:
            result = self._service_registry.purchase_bill_posting_service.post_bill(
                active_company.company_id,
                bill.id,
            )
            self.reload_bills(bill.id)
            show_info(
                self,
                "Bill Posted",
                f"Bill {result.bill_number} posted successfully.\nJournal entry: {result.journal_entry_number}",
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
                handle_document_sequence_error(
                    self, self._service_registry, exc,
                    "purchase_bill.post",
                    lambda: {"document_id": bill.id},
                    nav_ids.PURCHASE_BILLS,
                    active_company.company_name,
                )
                return
            if exc.app_error_code == AppErrorCode.MISSING_ACCOUNT_ROLE_MAPPING:
                coordinator = GuidedResolutionCoordinator(
                    resolver=ErrorResolutionResolver(),
                    workflow_resume_service=self._service_registry.workflow_resume_service,
                    navigation_service=self._service_registry.navigation_service,
                )
                coordinator.handle_exception(
                    parent=self,
                    error=exc,
                    workflow_key="purchase_bill.post",
                    workflow_snapshot=lambda: {"document_id": bill.id},
                    origin_nav_id=nav_ids.PURCHASE_BILLS,
                    resolution_context={"company_name": active_company.company_name},
                )
                return
            show_error(self, "Post Bill", f"Bill cannot be posted.\n\n{exc}")
        except PeriodLockedError as exc:
            show_error(self, "Post Bill", f"Bill cannot be posted.\n\n{exc}")
        except Exception as exc:
            show_error(self, "Post Bill", f"An error occurred.\n\n{exc}")

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate_to(nav_ids.COMPANIES)

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        token_payload = consume_resume_payload_for_workflows(
            context=context,
            service_registry=self._service_registry,
            allowed_workflow_keys=("purchase_bill.preflight", "purchase_bill.post"),
        )
        if token_payload is None:
            self._pending_resume_payload = None
            return
        self._pending_resume_payload = token_payload
        QTimer.singleShot(0, self._open_from_resume_payload)

    def _open_from_resume_payload(self) -> None:
        payload = self._pending_resume_payload
        if payload is None:
            return
        self._pending_resume_payload = None
        active_company = self._active_company()
        if active_company is None:
            return
        if payload.workflow_key == "purchase_bill.post":
            document_id = payload.payload.get("document_id") if payload.payload else None
            self.reload_bills(selected_bill_id=document_id)
            return
        self._open_create_dialog()

    # ------------------------------------------------------------------
    # Print / export
    # ------------------------------------------------------------------

    def _print_selected_bill(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        selected_bill = self._bills[self._table.currentRow()] if self._table.currentRow() >= 0 else None
        if selected_bill is None:
            return
        result = PrintExportDialog.show_dialog(self, f"Purchase Bill — {selected_bill.bill_number}")
        if result is None:
            return
        try:
            self._service_registry.purchase_bill_print_service.print_bill(
                active_company.company_id, selected_bill.id, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Purchase Bills", f"Export failed.\n\n{exc}")

    def _print_bill_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._bills:
            return
        result = PrintExportDialog.show_dialog(self, "Purchase Bill Register")
        if result is None:
            return
        try:
            self._service_registry.purchase_bill_print_service.print_bill_list(
                active_company.company_id, self._bills, result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Purchase Bills", f"Export failed.\n\n{exc}")
