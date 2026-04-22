from __future__ import annotations

import logging

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.sales.dto.sales_invoice_commands import (
    CreateSalesInvoiceCommand,
    SalesInvoiceLineCommand,
    UpdateSalesInvoiceCommand,
)
from seeker_accounting.modules.sales.dto.sales_invoice_dto import SalesInvoiceDetailDTO
from seeker_accounting.modules.sales.ui.sales_invoice_lines_grid import SalesInvoiceLinesGrid
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.document import DocumentWorkspace, DocumentWorkspaceSpec
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class SalesInvoiceDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        invoice_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._invoice_id = invoice_id
        self._saved_invoice: SalesInvoiceDetailDTO | None = None

        is_edit = invoice_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Sales Invoice - {company_name}")
        self.setModal(True)
        self.resize(1040, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._workspace = DocumentWorkspace(
            DocumentWorkspaceSpec(
                document_type_label="Sales Invoice",
                show_command_row=True,
                show_identity_strip=True,
                show_metadata_strip=True,
                show_totals_dock=True,
                show_action_rail=True,
            ),
            self,
        )
        layout.addWidget(self._workspace, 1)

        self._status_chip = self._build_status_chip("Draft", "warning")
        self._build_command_row(is_edit)
        self._build_metadata()
        self._workspace.set_lines_widget(self._build_lines_section())
        self._build_totals_dock()

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._build_action_rail(is_edit)

        self._refresh_identity()

        self._load_reference_data()
        if is_edit:
            self._load_invoice()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.sales_invoice")

    @property
    def saved_invoice(self) -> SalesInvoiceDetailDTO | None:
        return self._saved_invoice

    @classmethod
    def create_invoice(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> SalesInvoiceDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_invoice
        return None

    @classmethod
    def edit_invoice(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        invoice_id: int,
        parent: QWidget | None = None,
    ) -> SalesInvoiceDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, invoice_id=invoice_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_invoice
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_status_chip(self, text: str, tone: str) -> QLabel:
        chip = QLabel(text.upper(), self)
        chip.setProperty("chipTone", tone)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return chip

    def _build_command_row(self, is_edit: bool) -> None:
        row = self._workspace.command_row
        row_layout = row.layout()

        caption = QLabel("Draft workspace", row)
        caption.setObjectName("PanelHeaderCaption")
        row_layout.addWidget(caption)
        row_layout.addStretch(1)

        recalc_button = QPushButton("Recalculate", row)
        recalc_button.setProperty("variant", "ghost")
        recalc_button.clicked.connect(self._update_totals)
        row_layout.addWidget(recalc_button)

        save_button = QPushButton("Save Draft" if not is_edit else "Save Changes", row)
        save_button.setProperty("variant", "primary")
        save_button.clicked.connect(self._handle_submit)
        row_layout.addWidget(save_button)

    def _build_metadata(self) -> None:
        strip = self._workspace.metadata_strip

        self._customer_combo = SearchableComboBox(strip)
        self._workspace.add_metadata_pair(0, "Customer", self._customer_combo)

        self._reference_input = QLineEdit(strip)
        self._reference_input.setPlaceholderText("Optional reference")
        self._workspace.add_metadata_pair(1, "Reference", self._reference_input)

        self._invoice_date_edit = QDateEdit(strip)
        self._invoice_date_edit.setCalendarPopup(True)
        self._invoice_date_edit.setDate(date.today())
        self._workspace.add_metadata_pair(2, "Invoice Date", self._invoice_date_edit)

        self._due_date_edit = QDateEdit(strip)
        self._due_date_edit.setCalendarPopup(True)
        self._due_date_edit.setDate(date.today())
        self._workspace.add_metadata_pair(3, "Due Date", self._due_date_edit)

        self._currency_combo = SearchableComboBox(strip)
        self._workspace.add_metadata_pair(4, "Currency", self._currency_combo)

        self._exchange_rate_input = QLineEdit(strip)
        self._exchange_rate_input.setPlaceholderText("Base currency")
        self._exchange_rate_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._exchange_rate_input.setEnabled(False)
        self._workspace.add_metadata_pair(5, "Rate", self._exchange_rate_input)

        self._contract_combo = SearchableComboBox(strip)
        self._workspace.add_metadata_pair(6, "Contract", self._contract_combo)

        self._project_combo = SearchableComboBox(strip)
        self._workspace.add_metadata_pair(7, "Project", self._project_combo)

        self._notes_input = QPlainTextEdit(strip)
        self._notes_input.setMinimumHeight(56)
        self._notes_input.setMaximumHeight(84)
        self._notes_input.setPlaceholderText("Notes")
        self._workspace.add_metadata_full_row(8, "Notes", self._notes_input)

    def _build_lines_section(self) -> QWidget:
        self._lines_grid = SalesInvoiceLinesGrid(self._service_registry, self._company_id, self)
        return self._lines_grid

    def _build_totals_dock(self) -> None:
        dock = self._workspace.totals_dock
        dock_layout = dock.layout()

        self._line_count_label = QLabel("0 lines", dock)
        self._line_count_label.setObjectName("MetaLabel")
        dock_layout.addWidget(self._line_count_label)

        def add_row(label_text: str, value_object: str) -> QLabel:
            row = QFrame(dock)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            lbl = QLabel(label_text, row)
            lbl.setObjectName("MetaLabel")
            row_layout.addWidget(lbl)
            row_layout.addStretch(1)
            value = QLabel("0.00", row)
            value.setObjectName(value_object)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(value)
            dock_layout.addWidget(row)
            return value

        self._subtotal_value = add_row("Subtotal", "MetaValue")
        self._tax_value = add_row("Tax", "MetaValue")

        separator = QFrame(dock)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("TotalsSeparator")
        dock_layout.addWidget(separator)

        self._total_value = add_row("Total", "TotalsGrandTotal")
        dock_layout.addStretch(1)

    def _build_action_rail(self, is_edit: bool) -> None:
        rail = self._workspace.action_rail
        rail_layout = rail.layout()

        rail_layout.addStretch(1)

        cancel_button = QPushButton("Cancel", rail)
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        rail_layout.addWidget(cancel_button)

        save_button = QPushButton("Save Changes" if is_edit else "Create Invoice", rail)
        save_button.setProperty("variant", "primary")
        save_button.clicked.connect(self._handle_submit)
        rail_layout.addWidget(save_button)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            customers = self._service_registry.customer_service.list_customers(
                self._company_id, active_only=True
            )
            self._customer_combo.set_items(
                [(f"{c.customer_code} - {c.display_name}", c.id) for c in customers],
                placeholder="-- Select customer --",
                search_texts=[f"{c.customer_code} {c.display_name}" for c in customers],
            )

            contracts = self._service_registry.contract_service.list_contracts(self._company_id)
            self._contract_combo.set_items(
                [
                    (f"{c.contract_number} - {c.contract_title}", c.id)
                    for c in contracts
                ],
                placeholder="-- No contract --",
            )

            projects = self._service_registry.project_service.list_projects(self._company_id)
            self._project_combo.set_items(
                [
                    (f"{p.project_code} - {p.project_name}", p.id)
                    for p in projects
                ],
                placeholder="-- No project --",
            )

            currencies = self._service_registry.reference_data_service.list_active_currencies()
            self._currency_combo.set_items(
                [(currency.code, currency.code) for currency in currencies],
                placeholder="-- Select currency --",
            )

            base_currency_code = self._base_currency_code()
            if base_currency_code:
                self._currency_combo.set_current_value(base_currency_code)

            self._customer_combo.value_changed.connect(self._on_data_changed)
            self._contract_combo.value_changed.connect(self._on_data_changed)
            self._project_combo.value_changed.connect(self._on_data_changed)
            self._invoice_date_edit.dateChanged.connect(self._on_data_changed)
            self._due_date_edit.dateChanged.connect(self._on_data_changed)
            self._currency_combo.value_changed.connect(self._on_currency_changed)
            self._exchange_rate_input.textChanged.connect(self._on_data_changed)
            self._reference_input.textChanged.connect(self._on_data_changed)
            self._notes_input.textChanged.connect(self._on_data_changed)
            self._lines_grid.lines_changed.connect(self._on_data_changed)
            self._on_currency_changed(self._currency_combo.current_value())
        except Exception as exc:
            self._show_error(f"Failed to load reference data: {exc}")

    def _base_currency_code(self) -> str | None:
        try:
            ctx = self._service_registry.active_company_context
            return ctx.base_currency_code if ctx else None
        except Exception:
            return None

    def _load_invoice(self) -> None:
        if self._invoice_id is None:
            return
        try:
            detail = self._service_registry.sales_invoice_service.get_sales_invoice(
                self._company_id, self._invoice_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._customer_combo.set_current_value(detail.customer_id)
        self._contract_combo.set_current_value(detail.contract_id)
        self._project_combo.set_current_value(detail.project_id)

        self._invoice_date_edit.setDate(detail.invoice_date)
        self._due_date_edit.setDate(detail.due_date)

        self._currency_combo.set_current_value(detail.currency_code)

        if detail.exchange_rate is not None:
            self._exchange_rate_input.setText(str(detail.exchange_rate))

        self._reference_input.setText(detail.reference_number or "")
        self._notes_input.setPlainText(detail.notes or "")
        self._lines_grid.set_lines(detail.lines)

        self._on_currency_changed(self._currency_combo.current_value())
        self._update_totals()
        self._refresh_identity()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_data_changed(self, *_args: object) -> None:
        self._update_totals()
        self._refresh_identity()

    def _on_currency_changed(self, _value: object) -> None:
        current_currency = self._currency_combo.current_value()
        base_currency = self._base_currency_code()
        is_base_currency = bool(current_currency) and current_currency == base_currency

        if is_base_currency:
            self._exchange_rate_input.clear()
            self._exchange_rate_input.setEnabled(False)
            self._exchange_rate_input.setPlaceholderText("Base currency")
        else:
            self._exchange_rate_input.setEnabled(True)
            self._exchange_rate_input.setPlaceholderText("Required for foreign currency")

        self._update_totals()

    def _update_totals(self) -> None:
        subtotal, tax_total, total, line_count = self._lines_grid.calculate_totals()
        self._line_count_label.setText("1 line" if line_count == 1 else f"{line_count} lines")
        self._subtotal_value.setText(f"{subtotal:,.2f}")
        self._tax_value.setText(f"{tax_total:,.2f}")
        self._total_value.setText(f"{total:,.2f}")

    def _refresh_identity(self) -> None:
        invoice_date = self._invoice_date_edit.date().toPython() if hasattr(self, "_invoice_date_edit") else None
        due_date = self._due_date_edit.date().toPython() if hasattr(self, "_due_date_edit") else None

        dates_text = ""
        if invoice_date is not None and due_date is not None:
            dates_text = f"{invoice_date.strftime('%d %b %Y')} / Due {due_date.strftime('%d %b %Y')}"

        counterparty = ""
        if hasattr(self, "_customer_combo"):
            counterparty = self._customer_combo.currentText().strip()

        self._workspace.set_identity(
            document_label="Sales Invoice",
            document_number="New" if self._invoice_id is None else f"#{self._invoice_id}",
            status_widget=self._status_chip,
            dates_text=dates_text,
            counterparty=counterparty,
        )

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        customer_id = self._customer_combo.current_value()
        if not customer_id:
            self._show_error("Customer is required")
            return

        invoice_date = self._invoice_date_edit.date().toPython()
        due_date = self._due_date_edit.date().toPython()
        currency_code = self._currency_combo.current_value()
        if not currency_code:
            self._show_error("Currency is required")
            return

        exchange_rate: Decimal | None = None
        if self._exchange_rate_input.text().strip():
            try:
                exchange_rate = Decimal(self._exchange_rate_input.text().replace(",", "").strip())
            except InvalidOperation:
                self._show_error("Invalid exchange rate")
                return

        reference_number = self._reference_input.text().strip() or None
        notes = self._notes_input.toPlainText().strip() or None
        contract_id = self._contract_combo.current_value()
        project_id = self._project_combo.current_value()

        line_commands = self._lines_grid.get_line_commands()
        if not line_commands:
            self._show_error("At least one invoice line is required.")
            return

        try:
            if self._invoice_id is None:
                cmd = CreateSalesInvoiceCommand(
                    customer_id=customer_id,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    reference_number=reference_number,
                    notes=notes,
                    contract_id=contract_id,
                    project_id=project_id,
                    lines=tuple(line_commands),
                )
                self._saved_invoice = self._service_registry.sales_invoice_service.create_draft_invoice(
                    self._company_id, cmd
                )
            else:
                cmd_update = UpdateSalesInvoiceCommand(
                    customer_id=customer_id,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    reference_number=reference_number,
                    notes=notes,
                    contract_id=contract_id,
                    project_id=project_id,
                    lines=tuple(line_commands),
                )
                self._saved_invoice = self._service_registry.sales_invoice_service.update_draft_invoice(
                    self._company_id, self._invoice_id, cmd_update
                )
            self.accept()
        except (ValidationError, Exception) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
