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
from seeker_accounting.modules.sales.dto.sales_invoice_dto import SalesInvoiceListItemDTO
from seeker_accounting.modules.sales.ui.sales_invoice_dialog import SalesInvoiceDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)
from seeker_accounting.shared.ui.guided_resolution_coordinator import GuidedResolutionCoordinator
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.pager import Pager
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.register import RegisterPage
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


INVOICE_COLUMNS = (
    DataTableColumn(key="invoice_number", title="Invoice #"),
    DataTableColumn(key="invoice_date", title="Date"),
    DataTableColumn(key="due_date", title="Due Date"),
    DataTableColumn(key="customer", title="Customer"),
    DataTableColumn(key="currency", title="Currency"),
    DataTableColumn(key="total", title="Total", is_numeric=True),
    DataTableColumn(key="open_balance", title="Open Balance", is_numeric=True),
    DataTableColumn(key="status", title="Status"),
    DataTableColumn(key="payment", title="Payment"),
    DataTableColumn(key="posted_at", title="Posted At"),
)


_log = logging.getLogger(__name__)


class SalesInvoicesPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._invoices: list[SalesInvoiceListItemDTO] = []
        self._total_count: int = 0
        self._pending_resume_payload: ResumeTokenPayload | None = None
        self._command_enabled: dict[str, bool] = {
            "sales_invoices.new": False,
            "sales_invoices.edit": False,
            "sales_invoices.cancel": False,
            "sales_invoices.post": False,
            "sales_invoices.refresh": True,
            "sales_invoices.print": False,
            "sales_invoices.export_list": False,
        }
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(250)
        self._search_debounce.timeout.connect(lambda: self.reload_invoices(reset_page=True))

        self.setObjectName("SalesInvoicesPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        # Ribbon hosts the primary commands now; the ActionBand is hidden for
        # visual consistency with other migrated registers.
        self._register.action_band.hide()
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_invoices()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_invoices(
        self,
        selected_invoice_id: int | None = None,
        reset_page: bool = False,
    ) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._invoices = []
            self._total_count = 0
            self._invoices_model.removeRows(0, self._invoices_model.rowCount())
            self._record_count_label.setText("Select a company")
            self._pager.reset()
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        if reset_page:
            self._pager.reset()

        search_text = self._search_input.text().strip() or None
        try:
            page_result = self._service_registry.sales_invoice_service.list_sales_invoices_page(
                active_company.company_id,
                status_code=self._status_filter_value(),
                query=search_text,
                page=self._pager.page,
                page_size=self._pager.page_size,
            )
        except Exception as exc:
            self._invoices = []
            self._total_count = 0
            self._invoices_model.removeRows(0, self._invoices_model.rowCount())
            self._record_count_label.setText("Unable to load")
            self._pager.reset()
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Sales Invoices", f"Invoice data could not be loaded.\n\n{exc}")
            return

        self._invoices = list(page_result.items)
        self._total_count = page_result.total_count
        self._pager.apply_result(page_result)
        self._populate_table()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_invoice_id)
        self._update_action_state()

    def _handle_search_text_changed(self, _text: str) -> None:
        self._search_debounce.start()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._search_input = QLineEdit(register.toolbar_strip)
        self._search_input.setPlaceholderText("Search invoices…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(self._handle_search_text_changed)
        strip_layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Posted", "posted")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_invoices(reset_page=True))
        strip_layout.addWidget(self._status_filter_combo)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_invoices())
        strip_layout.addWidget(self._refresh_button)

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

        self._invoices_model = QStandardItemModel(0, len(INVOICE_COLUMNS), self)
        self._invoices_model.setHorizontalHeaderLabels([c.title for c in INVOICE_COLUMNS])

        self._table = DataTable(
            columns=INVOICE_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=True,
            show_column_chooser=True,
            selection_mode="single",
            empty_state_text="No invoices match the current filters.",
        )
        self._table.set_model(self._invoices_model)
        self._invoices_status_delegate = apply_status_chip_to_column(self._table.view(), 7)
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_row_activated)
        layout.addWidget(self._table, 1)

        self._pager = Pager(container, default_page_size=100)
        self._pager.page_changed.connect(lambda _p: self.reload_invoices())
        self._pager.page_size_changed.connect(lambda _s: self.reload_invoices(reset_page=True))
        layout.addWidget(self._pager)
        return container

    def _build_empty_state(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No sales invoices yet", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        summary = QLabel(
            "Create the first draft sales invoice, add line items with revenue accounts and tax codes, "
            "then post when the invoice is complete.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        actions = QWidget(card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        create_button = QPushButton("Create Invoice", actions)
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
            "Sales invoices are company-scoped. Choose the active company before creating or posting invoices.",
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
        if self._invoices:
            self._stack.setCurrentWidget(self._table_surface)
            return
        self._stack.setCurrentWidget(self._empty_state)

    @staticmethod
    def _make_item(text: str, *, user_data: object | None = None) -> QStandardItem:
        item = QStandardItem(text or "")
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value: Decimal) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _populate_table(self) -> None:
        self._invoices_model.removeRows(0, self._invoices_model.rowCount())
        for inv in self._invoices:
            items = [
                self._make_item(inv.invoice_number, user_data=inv.id),
                self._make_item(self._format_date(inv.invoice_date)),
                self._make_item(self._format_date(inv.due_date)),
                self._make_item(inv.customer_name or ""),
                self._make_item(inv.currency_code or ""),
                self._make_numeric(inv.total_amount),
                self._make_numeric(inv.open_balance_amount),
                self._make_item(inv.status_code),
                self._make_item((inv.payment_status_code or "").title()),
                self._make_item(self._format_datetime(inv.posted_at)),
            ]
            self._invoices_model.appendRow(items)

        search_text = self._search_input.text().strip()
        total = self._total_count
        shown = len(self._invoices)
        if search_text:
            self._record_count_label.setText(f"{shown} shown of {total} matches")
        else:
            self._record_count_label.setText(
                f"{total} invoice" if total == 1 else f"{total} invoices"
            )

    def _apply_search_filter(self) -> None:
        # Search is now handled server-side via reload_invoices. Kept as a
        # no-op for backward compatibility with any external callers.
        return

    def _restore_selection(self, selected_invoice_id: int | None) -> None:
        if not self._invoices:
            return
        if selected_invoice_id is None:
            target_idx = 0
        else:
            target_idx = next(
                (i for i, inv in enumerate(self._invoices) if inv.id == selected_invoice_id),
                0,
            )
        proxy = self._table.view().model()
        if proxy is None:
            return
        src_index = self._invoices_model.index(target_idx, 0)
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

    def _selected_invoice(self) -> SalesInvoiceListItemDTO | None:
        rows = self._table.selected_rows()
        if not rows:
            return None
        idx = rows[0]
        if 0 <= idx < len(self._invoices):
            return self._invoices[idx]
        return None

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Sales Invoices",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _set_command_enabled(self, command_id: str, enabled: bool) -> None:
        self._command_enabled[command_id] = bool(enabled)

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_invoice()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"
        permission_service = self._service_registry.permission_service

        self._set_command_enabled(
            "sales_invoices.new",
            has_company and permission_service.has_permission("sales.invoices.create"),
        )
        self._set_command_enabled(
            "sales_invoices.edit",
            is_draft and permission_service.has_permission("sales.invoices.edit"),
        )
        self._set_command_enabled(
            "sales_invoices.cancel",
            is_draft and permission_service.has_permission("sales.invoices.cancel"),
        )
        self._set_command_enabled(
            "sales_invoices.post",
            is_draft and permission_service.has_permission("sales.invoices.post"),
        )
        self._set_command_enabled("sales_invoices.refresh", True)
        self._set_command_enabled(
            "sales_invoices.print", has_company and selected is not None
        )
        self._set_command_enabled(
            "sales_invoices.export_list", has_company and bool(self._invoices)
        )
        self._notify_ribbon_state_changed()

    # ------------------------------------------------------------------
    # IRibbonHost
    # ------------------------------------------------------------------

    def _ribbon_commands(self):
        return {
            "sales_invoices.new": self._open_create_dialog,
            "sales_invoices.edit": self._open_edit_dialog,
            "sales_invoices.cancel": self._cancel_selected_draft,
            "sales_invoices.post": self._post_selected_invoice,
            "sales_invoices.refresh": self.reload_invoices,
            "sales_invoices.print": self._print_selected_invoice,
            "sales_invoices.export_list": self._print_invoice_list,
        }

    def ribbon_state(self):
        return dict(self._command_enabled)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_create_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.invoices.create"):
            self._show_permission_denied("sales.invoices.create")
            return
        active_company = self._active_company()
        if active_company is None:
            show_info(self, "Sales Invoices", "Select an active company before creating invoices.")
            return
        if not run_document_sequence_preflight(
            self, self._service_registry,
            active_company.company_id, active_company.company_name,
            "sales_invoice", nav_ids.SALES_INVOICES,
        ):
            return

        result = SalesInvoiceDialog.create_invoice(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            parent=self,
        )
        if result is not None:
            self.reload_invoices(selected_invoice_id=result.id)

    def _open_edit_dialog(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.invoices.edit"):
            self._show_permission_denied("sales.invoices.edit")
            return
        active_company = self._active_company()
        selected = self._selected_invoice()
        if active_company is None or selected is None:
            show_info(self, "Sales Invoices", "Select a draft invoice to edit.")
            return
        if selected.status_code != "draft":
            show_info(self, "Sales Invoices", "Only draft invoices can be edited.")
            return

        result = SalesInvoiceDialog.edit_invoice(
            self._service_registry,
            company_id=active_company.company_id,
            company_name=active_company.company_name,
            invoice_id=selected.id,
            parent=self,
        )
        if result is not None:
            self.reload_invoices(selected_invoice_id=result.id)

    def _cancel_selected_draft(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.invoices.cancel"):
            self._show_permission_denied("sales.invoices.cancel")
            return
        active_company = self._active_company()
        selected = self._selected_invoice()
        if active_company is None or selected is None:
            show_info(self, "Sales Invoices", "Select a draft invoice to cancel.")
            return

        choice = QMessageBox.question(
            self,
            "Cancel Draft Invoice",
            f"Cancel draft invoice {selected.invoice_number}?",
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service_registry.sales_invoice_service.cancel_draft_invoice(
                active_company.company_id, selected.id
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "Sales Invoices", str(exc))
            self.reload_invoices(selected_invoice_id=selected.id)
            return
        self.reload_invoices()

    def _post_selected_invoice(self) -> None:
        if not self._service_registry.permission_service.has_permission("sales.invoices.post"):
            self._show_permission_denied("sales.invoices.post")
            return
        active_company = self._active_company()
        selected = self._selected_invoice()
        if active_company is None or selected is None:
            show_info(self, "Sales Invoices", "Select a draft invoice to post.")
            return

        choice = QMessageBox.question(
            self,
            "Post Invoice",
            (
                f"Post invoice {selected.invoice_number}?\n\n"
                "Posting creates a journal entry, assigns a final invoice number, "
                "and makes the invoice immutable."
            ),
        )
        if choice != QMessageBox.StandardButton.Yes:
            return

        try:
            result = self._service_registry.sales_invoice_posting_service.post_invoice(
                active_company.company_id,
                selected.id,
                actor_user_id=self._service_registry.app_context.current_user_id,
            )
        except ValidationError as exc:
            if exc.app_error_code == AppErrorCode.MISSING_DOCUMENT_SEQUENCE:
                handle_document_sequence_error(
                    self, self._service_registry, exc,
                    "sales_invoice.post",
                    lambda: {"document_id": selected.id},
                    nav_ids.SALES_INVOICES,
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
                    workflow_key="sales_invoice.post",
                    workflow_snapshot=lambda: {"document_id": selected.id},
                    origin_nav_id=nav_ids.SALES_INVOICES,
                    resolution_context={"company_name": active_company.company_name},
                )
                return
            show_error(self, "Sales Invoices", str(exc))
            self.reload_invoices(selected_invoice_id=selected.id)
            return
        except (NotFoundError, PeriodLockedError) as exc:
            show_error(self, "Sales Invoices", str(exc))
            self.reload_invoices(selected_invoice_id=selected.id)
            return

        show_info(
            self,
            "Sales Invoices",
            f"Invoice {result.invoice_number} posted successfully.\n"
            f"Journal entry: {result.journal_entry_number}",
        )
        self.reload_invoices(selected_invoice_id=result.sales_invoice_id)

    def _open_companies_workspace(self) -> None:
        self._service_registry.navigation_service.navigate(nav_ids.COMPANIES)

    def _print_selected_invoice(self) -> None:
        active_company = self._active_company()
        selected = self._selected_invoice()
        if active_company is None or selected is None:
            return
        result = PrintExportDialog.show_dialog(self, f"Sales Invoice — {selected.invoice_number}")
        if result is None:
            return
        try:
            self._service_registry.sales_invoice_print_service.print_invoice(
                active_company.company_id, selected.id, result
            )
            show_info(self, "Export", f"Document saved to:\n{result.output_path}")
        except AppError as exc:
            show_error(self, "Export Failed", str(exc))

        except Exception:
            _log.exception("Export Failed")
            show_error(self, "Export Failed", "An unexpected error occurred. See application log for details.")

    def _print_invoice_list(self) -> None:
        active_company = self._active_company()
        if active_company is None or not self._invoices:
            return
        result = PrintExportDialog.show_dialog(self, "Sales Invoice Register")
        if result is None:
            return
        try:
            self._service_registry.sales_invoice_print_service.print_invoice_list(
                active_company.company_id, self._invoices, result
            )
            show_info(self, "Export", f"Document saved to:\n{result.output_path}")
        except AppError as exc:
            show_error(self, "Export Failed", str(exc))

        except Exception:
            _log.exception("Export Failed")
            show_error(self, "Export Failed", "An unexpected error occurred. See application log for details.")

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

    def _on_selection_changed(self, _rows: list[int]) -> None:
        self._update_action_state()

    def _on_row_activated(self, _row: int) -> None:
        selected = self._selected_invoice()
        if selected is None:
            return
        self._service_registry.navigation_service.navigate(
            nav_ids.SALES_INVOICE_DETAIL,
            context={"invoice_id": selected.id},
        )

    def _handle_active_company_changed(self, company_id: object, company_name: object) -> None:
        _ = company_id, company_name
        self.reload_invoices()

    def set_navigation_context(self, context: dict) -> None:
        from PySide6.QtCore import QTimer

        token_payload = consume_resume_payload_for_workflows(
            context=context,
            service_registry=self._service_registry,
            allowed_workflow_keys=("sales_invoice.preflight", "sales_invoice.post"),
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
        if payload.workflow_key == "sales_invoice.post":
            document_id = payload.payload.get("document_id") if payload.payload else None
            self.reload_invoices(selected_invoice_id=document_id)
            return
        self._open_create_dialog()
