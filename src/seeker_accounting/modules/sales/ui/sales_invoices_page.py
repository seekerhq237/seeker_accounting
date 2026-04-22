from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt
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
from seeker_accounting.modules.sales.dto.sales_invoice_dto import SalesInvoiceListItemDTO
from seeker_accounting.modules.sales.ui.sales_invoice_dialog import SalesInvoiceDialog
from seeker_accounting.app.navigation.workflow_resume_service import ResumeTokenPayload
from seeker_accounting.platform.exceptions import NotFoundError, PeriodLockedError, ValidationError
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver
from seeker_accounting.shared.ui.guided_resolution_coordinator import GuidedResolutionCoordinator
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.print_export_dialog import PrintExportDialog
from seeker_accounting.shared.ui.register import RegisterPage
from seeker_accounting.shared.ui.table_helpers import configure_dense_table
from seeker_accounting.shared.workflow.document_sequence_preflight import (
    consume_resume_payload_for_workflows,
    handle_document_sequence_error,
    run_document_sequence_preflight,
)


class SalesInvoicesPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._invoices: list[SalesInvoiceListItemDTO] = []
        self._pending_resume_payload: ResumeTokenPayload | None = None

        self.setObjectName("SalesInvoicesPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._register = RegisterPage(self)
        self._populate_toolbar_strip(self._register)
        self._populate_action_band(self._register)
        self._register.set_table_widget(self._build_content_stack())
        root_layout.addWidget(self._register)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._handle_active_company_changed
        )
        self.reload_invoices()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_invoices(self, selected_invoice_id: int | None = None) -> None:
        active_company = self._active_company()

        if active_company is None:
            self._invoices = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Select a company")
            self._stack.setCurrentWidget(self._no_active_company_state)
            self._update_action_state()
            return

        try:
            self._invoices = self._service_registry.sales_invoice_service.list_sales_invoices(
                active_company.company_id,
                status_code=self._status_filter_value(),
            )
        except Exception as exc:
            self._invoices = []
            self._table.setRowCount(0)
            self._record_count_label.setText("Unable to load")
            self._stack.setCurrentWidget(self._empty_state)
            self._update_action_state()
            show_error(self, "Sales Invoices", f"Invoice data could not be loaded.\n\n{exc}")
            return

        self._populate_table()
        self._apply_search_filter()
        self._sync_surface_state(active_company)
        self._restore_selection(selected_invoice_id)
        self._update_action_state()

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _populate_toolbar_strip(self, register: RegisterPage) -> None:
        strip_layout = register.toolbar_strip_layout

        self._search_input = QLineEdit(register.toolbar_strip)
        self._search_input.setPlaceholderText("Search invoices…")
        self._search_input.setFixedWidth(200)
        self._search_input.textChanged.connect(lambda _text: self._apply_search_filter())
        strip_layout.addWidget(self._search_input)

        self._status_filter_combo = QComboBox(register.toolbar_strip)
        self._status_filter_combo.addItem("All statuses", None)
        self._status_filter_combo.addItem("Draft", "draft")
        self._status_filter_combo.addItem("Posted", "posted")
        self._status_filter_combo.addItem("Cancelled", "cancelled")
        self._status_filter_combo.currentIndexChanged.connect(lambda _index: self.reload_invoices())
        strip_layout.addWidget(self._status_filter_combo)

        strip_layout.addStretch(1)

        self._record_count_label = QLabel(register.toolbar_strip)
        self._record_count_label.setObjectName("StatusRailText")
        strip_layout.addWidget(self._record_count_label)

        self._refresh_button = QPushButton("Refresh", register.toolbar_strip)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(lambda: self.reload_invoices())
        strip_layout.addWidget(self._refresh_button)

    def _populate_action_band(self, register: RegisterPage) -> None:
        band_layout = register.action_band_layout

        self._new_button = QPushButton("New Invoice", register.action_band)
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

        self._post_button = QPushButton("Post Invoice", register.action_band)
        self._post_button.setProperty("variant", "secondary")
        self._post_button.clicked.connect(self._post_selected_invoice)
        band_layout.addWidget(self._post_button)

        band_layout.addStretch(1)

        self._print_button = QPushButton("Print / Export", register.action_band)
        self._print_button.setProperty("variant", "ghost")
        self._print_button.clicked.connect(self._print_selected_invoice)
        band_layout.addWidget(self._print_button)

        self._export_list_button = QPushButton("Export List", register.action_band)
        self._export_list_button.setProperty("variant", "ghost")
        self._export_list_button.clicked.connect(self._print_invoice_list)
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
        layout.setSpacing(0)

        self._table = QTableWidget(container)
        self._table.setObjectName("SalesInvoicesTable")
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels((
            "Invoice #",
            "Date",
            "Due Date",
            "Customer",
            "Currency",
            "Total",
            "Open Balance",
            "Status",
            "Payment",
            "Posted At",
        ))
        configure_dense_table(self._table)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.itemDoubleClicked.connect(self._handle_item_double_clicked)
        layout.addWidget(self._table)
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

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for inv in self._invoices:
            row_index = self._table.rowCount()
            self._table.insertRow(row_index)
            values = (
                inv.invoice_number,
                self._format_date(inv.invoice_date),
                self._format_date(inv.due_date),
                inv.customer_name,
                inv.currency_code,
                self._format_amount(inv.total_amount),
                self._format_amount(inv.open_balance_amount),
                inv.status_code.title(),
                inv.payment_status_code.title(),
                self._format_datetime(inv.posted_at),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, inv.id)
                if col in {1, 2, 4, 5, 6, 7, 8, 9}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row_index, col, item)

        self._table.resizeColumnsToContents()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, header.ResizeMode.Stretch)
        header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, header.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)

        count = len(self._invoices)
        self._record_count_label.setText(f"{count} invoice" if count == 1 else f"{count} invoices")

    def _apply_search_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        for row in range(self._table.rowCount()):
            if not query:
                self._table.setRowHidden(row, False)
                continue
            match = False
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item is not None and query in item.text().lower():
                    match = True
                    break
            self._table.setRowHidden(row, not match)

    def _restore_selection(self, selected_invoice_id: int | None) -> None:
        if self._table.rowCount() == 0:
            return
        if selected_invoice_id is None:
            self._table.selectRow(0)
            return
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == selected_invoice_id:
                self._table.selectRow(row)
                return
        self._table.selectRow(0)

    def _selected_invoice(self) -> SalesInvoiceListItemDTO | None:
        current_row = self._table.currentRow()
        if current_row < 0:
            return None
        item = self._table.item(current_row, 0)
        if item is None:
            return None
        invoice_id = item.data(Qt.ItemDataRole.UserRole)
        for inv in self._invoices:
            if inv.id == invoice_id:
                return inv
        return None

    def _show_permission_denied(self, permission_code: str) -> None:
        show_error(
            self,
            "Sales Invoices",
            self._service_registry.permission_service.build_denied_message(permission_code),
        )

    def _update_action_state(self) -> None:
        active_company = self._active_company()
        selected = self._selected_invoice()
        has_company = active_company is not None
        is_draft = has_company and selected is not None and selected.status_code == "draft"
        permission_service = self._service_registry.permission_service

        self._new_button.setEnabled(
            has_company and permission_service.has_permission("sales.invoices.create")
        )
        self._edit_button.setEnabled(
            is_draft and permission_service.has_permission("sales.invoices.edit")
        )
        self._cancel_button.setEnabled(
            is_draft and permission_service.has_permission("sales.invoices.cancel")
        )
        self._post_button.setEnabled(
            is_draft and permission_service.has_permission("sales.invoices.post")
        )
        self._print_button.setEnabled(has_company and selected is not None)
        self._export_list_button.setEnabled(has_company and bool(self._invoices))

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
        except Exception as exc:
            show_error(self, "Export Failed", str(exc))

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
