from __future__ import annotations

import logging

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.purchases.dto.supplier_payment_dto import SupplierPaymentListItemDTO
from seeker_accounting.modules.purchases.ui.supplier_payment_dialog import SupplierPaymentDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.pager import Pager
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.register import RegisterPage
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


_log = logging.getLogger(__name__)


PAYMENT_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="payment_number", title="Payment #"),
    DataTableColumn(key="payment_date", title="Date"),
    DataTableColumn(key="supplier_name", title="Supplier"),
    DataTableColumn(key="financial_account_name", title="Account"),
    DataTableColumn(key="currency_code", title="Currency"),
    DataTableColumn(key="amount_paid", title="Amount", is_numeric=True),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="posted_at", title="Posted At"),
)
_STATUS_COLUMN_INDEX = 6


_CMD_NEW = "supplier_payments.new"
_CMD_EDIT = "supplier_payments.edit"
_CMD_CANCEL = "supplier_payments.cancel"
_CMD_POST = "supplier_payments.post"
_CMD_REFRESH = "supplier_payments.refresh"
_CMD_PRINT = "supplier_payments.print"
_CMD_EXPORT_LIST = "supplier_payments.export_list"


class SupplierPaymentsPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._payments: list[SupplierPaymentListItemDTO] = []
        self._total_count: int = 0
        self._pending_resume_payload: ResumeTokenPayload | None = None
        self._command_enabled: dict[str, bool] = {
            _CMD_NEW: False,
            _CMD_EDIT: False,
            _CMD_CANCEL: False,
            _CMD_POST: False,
            _CMD_REFRESH: True,
            _CMD_PRINT: False,
            _CMD_EXPORT_LIST: False,
        }

        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(lambda: self.reload_payments(reset_page=True))

        self.setObjectName("SupplierPaymentsPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        # Action band is owned by the ribbon now; the visible toolbar above
        # carries the legacy buttons. ActionBand stays hidden for visual
        # consistency with other migrated registers.
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_payments()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_payments(
        self,
        selected_payment_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._payments = []
            self._total_count = 0
            self._payments_model.removeRows(0, self._payments_model.rowCount())
            self._record_count_label.setText("Select a company")
            self._pager.reset()
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        if reset_page:
            self._pager.reset()

        search_text = self._search_input.text().strip() or None
        try:
            page_result = self._service_registry.supplier_payment_service.list_supplier_payments_page(
                active_company.company_id,
                status_code=self._status_filter_value(),
                query=search_text,
                page=self._pager.page,
                page_size=self._pager.page_size,
            )
        except Exception as exc:
            self._payments = []
            self._total_count = 0
            self._payments_model.removeRows(0, self._payments_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._pager.reset()
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Supplier Payments", f"Payment data could not be loaded.\n\n{exc}")
            return

        self._payments = list(page_result.items)
        self._total_count = page_result.total_count
        self._pager.apply_result(page_result)
        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_payment_id)
        self._update_action_state()

    def _handle_search_text_changed(self, _text: str) -> None:
        self._search_debounce.start()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        title = QLabel("Payment Register", register.toolbar_strip)
        title.setObjectName("ToolbarTitle")
        strip_layout.addWidget(title)

        self._search_input = QLineEdit(register.toolbar_strip)
        self._search_input.setPlaceholderText("Search payments…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        strip_layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Posted", "posted")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_payments(reset_page=True))
        strip_layout.addWidget(self._status_filter_combo)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._new_button = QPushButton("New Payment", register.toolbar_strip)
        self._new_button.setProperty("variant", "primary")
        self._new_button.clicked.connect(self._open_create_dialog)
        strip_layout.addWidget(self._new_button)

        self._edit_button = QPushButton("Edit Draft", register.toolbar_strip)
        self._edit_button.setProperty("variant", "secondary")
        self._edit_button.clicked.connect(self._open_edit_dialog)
        strip_layout.addWidget(self._edit_button)

        self._cancel_button = QPushButton("Cancel Draft", register.toolbar_strip)
        self._cancel_button.setProperty("variant", "secondary")
        self._cancel_button.clicked.connect(self._cancel_selected_draft)
        strip_layout.addWidget(self._cancel_button)

        self._post_button = QPushButton("Post Payment", register.toolbar_strip)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_payment)
        strip_layout.addWidget(self._post_button)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_payments())
        strip_layout.addWidget(self._refresh_button)

        self._print_button = QPushButton("Print / Export", register.toolbar_strip)
        self._print_button.setProperty("variant", "ghost")
        self._print_button.clicked.connect(self._print_selected_payment)
        strip_layout.addWidget(self._print_button)

        self._export_list_button = QPushButton("Export List", register.toolbar_strip)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._print_payment_list)
        strip_layout.addWidget(self._export_list_button)

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

        self._payments_model = QStandardItemModel(0, len(PAYMENT_COLUMNS), self)
        self._payments_model.setHorizontalHeaderLabels([c.title for c in PAYMENT_COLUMNS])

        self._table = DataTable(
            columns=PAYMENT_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No payments match the current filters.",
            parent=container,
        )
        self._table.set_model(self._payments_model)
        self._payments_status_delegate = apply_status_chip_to_column(
            self._table.view(), _STATUS_COLUMN_INDEX
        )
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        layout.addWidget(self._table, 1)

        self._pager = Pager(container, default_page_size=100)
        self._pager.page_changed.connect(lambda _p: self.reload_payments())
        self._pager.page_size_changed.connect(lambda _s: self.reload_payments(reset_page=True))
        layout.addWidget(self._pager)
        return container

    @staticmethod
    def _make_item(text: str, *, user_data=None) -> QStandardItem:
        item = QStandardItem(text or "")
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No supplier payments yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create a draft payment, allocate against open bills, then post to create journal entries.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Payment", actions)
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
            "Supplier payments are company-scoped. Choose the active company before recording payments.",
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
        if self._payments:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    def _populate_table(self) -> None:
        self._payments_model.removeRows(0, self._payments_model.rowCount())
        for p in self._payments:
            row_items = [
                self._make_item(p.payment_number, user_data=p.id),
                self._make_item(self._format_date(p.payment_date)),
                self._make_item(p.supplier_name),
                self._make_item(p.financial_account_name),
                self._make_item(p.currency_code),
                self._make_numeric(p.amount_paid),
                self._make_item(p.status_code or ""),
                self._make_item(self._format_datetime(p.posted_at)),
            ]
            self._payments_model.appendRow(row_items)

        search_text = self._search_input.text().strip()
        total = self._total_count
        shown = len(self._payments)
        if search_text:
            self._record_count_label.setText(f"{shown} shown of {total} matches")
        else:
            self._record_count_label.setText(
                f"{total} payment" if total == 1 else f"{total} payments"
            )

    def _apply_search_filter(self) -> None:
        # Search is server-side now via reload_payments. No-op kept for compatibility.
        return

    def _restore_selection(self, selected_payment_id: int | None) -> None:
        if not self._payments:
            return
        if selected_payment_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, p in enumerate(self._payments) if p.id == selected_payment_id),
                -1,
            )
        if target_idx < 0:
            target_idx = 0
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._payments_model.index(target_idx, 0)
        proxy_index = proxy.mapFromSource(src_index)
        if not proxy_index.isValid():
            return
        sm = self._table.view().selectionModel()
        if sm is None:
            return
        sm.select(
            proxy_index,
            sm.SelectionFlag.ClearAndSelect | sm.SelectionFlag.Rows,
        )
        self._table.view().scrollTo(proxy_index)

    def _selected_payment(self) -> SupplierPaymentListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._payments):
            return self._payments[idx]
        return None

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        selected = self._selected_payment()
        if selected is not None and selected.status_code == "draft":
            self._open_edit_dialog()

    def _set_command_enabled(self, command_id: str, enabled: bool) -> None:
        self._command_enabled[command_id] = bool(enabled)

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Supplier Payments",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_payment()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"
        permission_service = self._service_registry.permission_service

        new_enabled = has_company and permission_service.has_permission("purchases.payments.create")
        edit_enabled = is_draft and permission_service.has_permission("purchases.payments.edit")
        cancel_enabled = is_draft and permission_service.has_permission("purchases.payments.cancel")
        post_enabled = is_draft and permission_service.has_permission("purchases.payments.post")
        print_enabled = has_company and selected is not None
        export_enabled = has_company and bool(self._payments)

        self._new_button.setEnabled(new_enabled)
        self._edit_button.setEnabled(edit_enabled)
        self._cancel_button.setEnabled(cancel_enabled)
        self._post_button.setEnabled(post_enabled)
        self._print_button.setEnabled(print_enabled)
        self._export_list_button.setEnabled(export_enabled)

        self._set_command_enabled(_CMD_NEW, new_enabled)
        self._set_command_enabled(_CMD_EDIT, edit_enabled)
        self._set_command_enabled(_CMD_CANCEL, cancel_enabled)
        self._set_command_enabled(_CMD_POST, post_enabled)
        self._set_command_enabled(_CMD_REFRESH, True)
        self._set_command_enabled(_CMD_PRINT, print_enabled)
        self._set_command_enabled(_CMD_EXPORT_LIST, export_enabled)
        self._notify_ribbon_state_changed()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self):
        return {
            _CMD_NEW: self._open_create_dialog,
            _CMD_EDIT: self._open_edit_dialog,
            _CMD_CANCEL: self._cancel_selected_draft,
            _CMD_POST: self._post_selected_payment,
            _CMD_REFRESH: self.reload_payments,
            _CMD_PRINT: self._print_selected_payment,
            _CMD_EXPORT_LIST: self._print_payment_list,
        }

    def ribbon_state(self):
        return dict(self._command_enabled)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.payments.create"):
            self._show_permission_denied("purchases.payments.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Supplier Payments", "Select an active company before creating payments.")
            return
        if not run_document_sequence_preflight(
            self, self._service_registry,
            active_company.company_id, active_company.company_name,
            "supplier_payment", nav_ids.SUPPLIER_PAYMENTS,
        ):
            return

        result = SupplierPaymentDialog.create_payment(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_payments(selected_payment_id=result.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.payments.edit"):
            self._show_permission_denied("purchases.payments.edit")
            return
        active_company = self._active_company()
        selected = self._selected_payment()
        if active_company is None or selected is None:
            show_info(self, "Supplier Payments", "Select a draft payment to edit.")
            return
        if selected.status_code != "draft":
            show_info(self, "Supplier Payments", "Only draft payments can be edited.")
            return

        result = SupplierPaymentDialog.edit_payment(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            payment_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_payments(selected_payment_id=result.id)

    def _cancel_selected_draft(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.payments.cancel"):
            self._show_permission_denied("purchases.payments.cancel")
            return
        active_company = self._active_company()
        selected = self._selected_payment()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Cancel Draft Payment",
            f"Cancel draft payment {selected.payment_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.supplier_payment_service.cancel_draft_payment(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Supplier Payments", str(exc))
            self.reload_payments(selected_payment_id=selected.id)
            return
        self.reload_payments()

    def _post_selected_payment(self) -> None:
        if not self._service_registry.permission_service.has_permission("purchases.payments.post"):
            self._show_permission_denied("purchases.payments.post")
            return
        active_company = self._active_company()
        selected = self._selected_payment()
        if active_company is None or selected is None:
            return

        choice = QMessageBox.question(
            self,
            "Post Payment",
            (
                f"Post payment {selected.payment_number}?\n\n"
                "Posting creates a journal entry, assigns a final payment number, "
                "and updates bill payment statuses."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._service_registry.supplier_payment_posting_service.post_payment(
                active_company.company_id,
                selected.id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
                handle_document_sequence_error(
                    self, self._service_registry, exc,
                    "supplier_payment.post",
                    lambda: {"document_id": selected.id},
                    nav_ids.SUPPLIER_PAYMENTS,
                    active_company.company_name,
                )
                return
            show_error(self, "Supplier Payments", str(exc))
            self.reload_payments(selected_payment_id=selected.id)
            return
        except (NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Supplier Payments", str(exc))
            self.reload_payments(selected_payment_id=selected.id)
            return

        show_info(
            self,
            "Supplier Payments",
            f"Payment {result.payment_number} posted successfully.\n"
            f"Journal entry: {result.journal_entry_number}",
        )
        self.reload_payments(selected_payment_id=result.supplier_payment_id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

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

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_payments()

    def set_navigation_context(self, context: dict) -> None:
        token_payload = consume_resume_payload_for_workflows(
            context=context,
            service_registry=self._service_registry,
            allowed_workflow_keys=("supplier_payment.preflight", "supplier_payment.post"),
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
        if payload.workflow_key == "supplier_payment.post":
            document_id = payload.payload.get("document_id") if payload.payload else None
            self.reload_payments(selected_payment_id=document_id)
            return
        self._open_create_dialog()

    # ------------------------------------------------------------------
    # Print / export
    # ------------------------------------------------------------------

    def _print_selected_payment(self) -> None:
        active_company = self._active_company()
        if active_company is None:
            return
        selected = self._selected_payment()
        if selected is None:
            return
        result = PrintExportDialog.show_dialog(self, f"Supplier Payment — {selected.payment_number}")
        if result is None:
            return
        try:
            self._service_registry.supplier_payment_print_service.print_payment(
                active_company.company_id, selected.id, result,
            )
            result.open_file()
        except AppError as exc:
            show_error(self, "Supplier Payments", f"Export failed.\n\n{exc}")

        except Exception:
            _log.exception("Supplier Payments")
            show_error(self, "Supplier Payments", "An unexpected error occurred. See application log for details.")

    def _print_payment_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._payments:
            return
        result = PrintExportDialog.show_dialog(self, "Supplier Payment Register")
        if result is None:
            return
        try:
            self._service_registry.supplier_payment_print_service.print_payment_list(
                active_company.company_id, self._payments, result,
            )
            result.open_file()
        except AppError as exc:
            show_error(self, "Supplier Payments", f"Export failed.\n\n{exc}")

        except Exception:
            _log.exception("Supplier Payments")
            show_error(self, "Supplier Payments", "An unexpected error occurred. See application log for details.")
