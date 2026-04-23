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
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.sales.dto.customer_receipt_dto import CustomerReceiptListItemDTO
from seeker_accounting.modules.sales.ui.customer_receipt_dialog import CustomerReceiptDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.pager import Pager
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.table_helpers import configure_compact_table
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


class CustomerReceiptsPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._receipts: list[CustomerReceiptListItemDTO] = []
        self._total_count: int = 0
        self._pending_resume_payload: ResumeTokenPayload | None = None
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(lambda: self.reload_receipts(reset_page=True))

        self.setObjectName("CustomerReceiptsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(16)

        root_layout.addWidget(self._build_action_bar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_receipts()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_receipts(
        self,
        selected_receipt_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._receipts = []
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
            page_result = self._service_registry.customer_receipt_service.list_customer_receipts_page(
                active_company.company_id,
                status_code=self._status_filter_value(),
                query=search_text,
                page=self._pager.page,
                page_size=self._pager.page_size,
            )
        except Exception as exc:
            self._receipts = []
            self._total_count = 0
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._pager.reset()
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Customer Receipts", f"Receipt data could not be loaded.\n\n{exc}")
            return

        self._receipts = list(page_result.items)
        self._total_count = page_result.total_count
        self._pager.apply_result(page_result)
        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_receipt_id)
        self._update_action_state()

    def _handle_search_text_changed(self, _text: str) -> None:
        self._search_debounce.start()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        self._search_input = QLineEdit(card)
        self._search_input.setPlaceholderText("Search receipts...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(card)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Posted", "posted")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_receipts(reset_page=True))
        layout.addWidget(self._status_filter_combo)

        self._new_button = QPushButton("New Receipt", card)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", card)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        layout.addWidget(self._edit_button)

        self._cancel_button = QPushButton("Cancel Draft", card)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_draft)
        layout.addWidget(self._cancel_button)

        self._post_button = QPushButton("Post Receipt", card)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_receipt)
        layout.addWidget(self._post_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_receipts())
        layout.addWidget(self._refresh_button)

        self._print_button = QPushButton("Print / Export", card)
        self._print_button.setProperty("variant", "ghost")
        self._print_button.clicked.connect(self._print_selected_receipt)
        layout.addWidget(self._print_button)

        self._export_list_button = QPushButton("Export List", card)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._print_receipt_list)
        layout.addWidget(self._export_list_button)
        return card

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
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        top_row = QWidget(card)
        top_row_layout = QHBoxLayout(top_row)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(12)

        title = QLabel("Receipt Register", top_row)
        title.setObjectName("CardTitle")
        top_row_layout.addWidget(title)
        top_row_layout.addStretch(1)

        self._record_count_label = QLabel(top_row)
        self._record_count_label.setObjectName("ToolbarMeta")
        top_row_layout.addWidget(self._record_count_label)

        layout.addWidget(top_row)

        self._table = QTableWidget(card)
        self._table.setObjectName("CustomerReceiptsTable")
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels((
            "Receipt #",
            "Date",
            "Customer",
            "Account",
            "Currency",
            "Amount",
            "Status",
            "Posted At",
        ))
        configure_compact_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._table)

        self._pager = Pager(card, default_page_size=100)
        self._pager.page_changed.connect(lambda _p: self.reload_receipts())
        self._pager.page_size_changed.connect(lambda _s: self.reload_receipts(reset_page=True))
        layout.addWidget(self._pager)
        return card

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No customer receipts yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create a draft receipt, allocate against open invoices, then post to create journal entries.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Receipt", actions)
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
            "Customer receipts are company-scoped. Choose the active company before recording payments.",
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

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _status_filter_value(self) -> str | None:
        value = self._status_filter_combo.currentData()
        return value if isinstance(value, str) and value else None

    def _sync_surface_state(self, active_company: ActiveCompanyDTO | None) -> None:
        if active_company is None:
            self._stack.setCurrentWidget(self._no_active_company_state)
            return
        if self._receipts:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._table.setUpdatesEnabled(False)
        self._table.setSortingEnabled(False)
        try:
            self._table.setRowCount(len(self._receipts))
            for row_index, r in enumerate(self._receipts):
                values = (
                    r.receipt_number,
                    self._format_date(r.receipt_date),
                    r.customer_name,
                    r.financial_account_name,
                    r.currency_code,
                    self._format_amount(r.amount_received),
                    r.status_code.title(),
                    self._format_datetime(r.posted_at),
                )
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, r.id)
                    if col in {1, 4, 6, 7}:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if col == 5:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self._table.setItem(row_index, col, item)

            self._table.resizeColumnsToContents()
            header = self._table.horizontalHeader()
            header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, header.ResizeMode.Stretch)
            header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        finally:
            self._table.setSortingEnabled(True)
            self._table.setUpdatesEnabled(True)

        search_text = self._search_input.text().strip()
        total = self._total_count
        shown = len(self._receipts)
        if search_text:
            self._record_count_label.setText(f"{shown} shown of {total} matches")
        else:
            self._record_count_label.setText(
                f"{total} receipt" if total == 1 else f"{total} receipts"
            )

    def _apply_search_filter(self) -> None:
        # Search is server-side now via reload_receipts. No-op kept for compatibility.
        return

    def _restore_selection(self, selected_receipt_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_receipt_id is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_receipt_id:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    def _selected_receipt(self) -> CustomerReceiptListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        receipt_id = item.data(Qt.ItemDataRole.UserRole)
        for r in self._receipts:
            if r.id == receipt_id:
                return r
        return None

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Customer Receipts",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_receipt()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_company and permission_service.has_permission("sales.receipts.create")
        )
        self._edit_button.setEnabled(
            is_draft and permission_service.has_permission("sales.receipts.edit")
        )
        self._cancel_button.setEnabled(
            is_draft and permission_service.has_permission("sales.receipts.cancel")
        )
        self._post_button.setEnabled(
            is_draft and permission_service.has_permission("sales.receipts.post")
        )
        self._print_button.setEnabled(has_company and selected is not None)
        self._export_list_button.setEnabled(has_company and bool(self._receipts))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.receipts.create"):
            self._show_permission_denied("sales.receipts.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Customer Receipts", "Select an active company before creating receipts.")
            return
        if not run_document_sequence_preflight(
            self, self._service_registry,
            active_company.company_id, active_company.company_name,
            "customer_receipt", nav_ids.CUSTOMER_RECEIPTS,
        ):
            return

        result = CustomerReceiptDialog.create_receipt(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_receipts(selected_receipt_id=result.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.receipts.edit"):
            self._show_permission_denied("sales.receipts.edit")
            return
        active_company = self._active_company()
        selected = self._selected_receipt()
        if active_company is None or selected is None:
            show_info(self, "Customer Receipts", "Select a draft receipt to edit.")
            return
        if selected.status_code != "draft":
            show_info(self, "Customer Receipts", "Only draft receipts can be edited.")
            return

        result = CustomerReceiptDialog.edit_receipt(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            receipt_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_receipts(selected_receipt_id=result.id)

    def _cancel_selected_draft(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.receipts.cancel"):
            self._show_permission_denied("sales.receipts.cancel")
            return
        active_company = self._active_company()
        selected = self._selected_receipt()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Cancel Draft Receipt",
            f"Cancel draft receipt {selected.receipt_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.customer_receipt_service.cancel_draft_receipt(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Customer Receipts", str(exc))
            self.reload_receipts(selected_receipt_id=selected.id)
            return
        self.reload_receipts()

    def _post_selected_receipt(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.receipts.post"):
            self._show_permission_denied("sales.receipts.post")
            return
        active_company = self._active_company()
        selected = self._selected_receipt()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Post Receipt",
            (
                f"Post receipt {selected.receipt_number}?\n\n"
                "Posting creates a journal entry, assigns a final receipt number, "
                "and updates invoice payment statuses."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._service_registry.customer_receipt_posting_service.post_receipt(
                active_company.company_id,
                selected.id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
                handle_document_sequence_error(
                    self, self._service_registry, exc,
                    "customer_receipt.post",
                    lambda: {"document_id": selected.id},
                    nav_ids.CUSTOMER_RECEIPTS,
                    active_company.company_name,
                )
                return
            show_error(self, "Customer Receipts", str(exc))
            self.reload_receipts(selected_receipt_id=selected.id)
            return
        except (NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Customer Receipts", str(exc))
            self.reload_receipts(selected_receipt_id=selected.id)
            return

        show_info(
            self,
            "Customer Receipts",
            f"Receipt {result.receipt_number} posted successfully.\n"
            f"Journal entry: {result.journal_entry_number}",
        )
        self.reload_receipts(selected_receipt_id=result.customer_receipt_id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _print_selected_receipt(self) -> None:
        active_company = self._active_company()
        selected = self._selected_receipt()
        if active_company is None or selected is None:
            return
        result = PrintExportDialog.show_dialog(self, f"Customer Receipt — {selected.receipt_number}")
        if result is None:
            return
        try:
            self._service_registry.customer_receipt_print_service.print_receipt(
                active_company.company_id, selected.id, result
            )
            show_info(self, "Export", f"Document saved to:\n{result.output_path}")
        except Exception as exc:
            show_error(self, "Export Failed", str(exc))

    def _print_receipt_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._receipts:
            return
        result = PrintExportDialog.show_dialog(self, "Customer Receipt Register")
        if result is None:
            return
        try:
            self._service_registry.customer_receipt_print_service.print_receipt_list(
                active_company.company_id, self._receipts, result
            )
            show_info(self, "Export", f"Document saved to:\n{result.output_path}")
        except Exception as exc:
            show_error(self, "Export Failed", str(exc))

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _format_date(self, value: date) -> str:
        return value.strftime("%Y-%m-%d")

    def _format_datetime(self, value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value is not None else ""

    def _format_amount(self, value: Decimal) -> str:
        return f"{value:,.2f}"

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _handle_item_double_clicked(self, *_args: object) -> None:
        selected = self._selected_receipt()
        if selected is not None and selected.status_code == "draft":
            self._open_edit_dialog()

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_receipts()

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        token_payload = consume_resume_payload_for_workflows(
            context=context,
            service_registry=self._service_registry,
            allowed_workflow_keys=("customer_receipt.preflight", "customer_receipt.post"),
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
        if payload.workflow_key == "customer_receipt.post":
            document_id = payload.payload.get("document_id") if payload.payload else None
            self.reload_receipts(selected_receipt_id=document_id)
            return
        self._open_create_dialog()
