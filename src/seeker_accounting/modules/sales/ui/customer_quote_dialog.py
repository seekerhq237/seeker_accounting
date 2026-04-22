from __future__ import annotations

import logging

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.sales.dto.customer_quote_commands import (
    ConvertCustomerQuoteCommand,
    CreateCustomerQuoteCommand,
    CustomerQuoteLineCommand,
    UpdateCustomerQuoteCommand,
)
from seeker_accounting.modules.sales.dto.customer_quote_dto import (
    CustomerQuoteConversionResultDTO,
    CustomerQuoteDetailDTO,
)
from seeker_accounting.modules.sales.ui.customer_quote_lines_grid import CustomerQuoteLinesGrid
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.forms import create_field_block
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class CustomerQuoteDialog(QDialog):
    """Create or edit a draft customer quote."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        quote_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._quote_id = quote_id
        self._saved_quote: CustomerQuoteDetailDTO | None = None

        is_edit = quote_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Customer Quote - {company_name}")
        self.setModal(True)
        self.resize(960, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        layout.addWidget(self._build_header_section())
        layout.addWidget(self._build_lines_section(), 1)
        layout.addWidget(self._build_totals_panel())

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._button_box.accepted.connect(self._handle_submit)
        self._button_box.rejected.connect(self.reject)
        save_button = self._button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Create Quote" if not is_edit else "Save Changes")
            save_button.setProperty("variant", "primary")
        cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")
        layout.addWidget(self._button_box)

        self._load_reference_data()
        if is_edit:
            self._load_quote()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.customer_quote")

    @property
    def saved_quote(self) -> CustomerQuoteDetailDTO | None:
        return self._saved_quote

    @classmethod
    def create_quote(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> CustomerQuoteDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_quote
        return None

    @classmethod
    def edit_quote(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        quote_id: int,
        parent: QWidget | None = None,
    ) -> CustomerQuoteDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, quote_id=quote_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_quote
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_header_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        grid = QGridLayout(card)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setSpacing(6)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)

        # Row 0: Customer | Quote Date + Expiry Date
        self._customer_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Customer", self._customer_combo), 0, 0)

        dates_row = QWidget(card)
        dates_layout = QHBoxLayout(dates_row)
        dates_layout.setContentsMargins(0, 0, 0, 0)
        dates_layout.setSpacing(10)

        self._quote_date_edit = QDateEdit(card)
        self._quote_date_edit.setCalendarPopup(True)
        self._quote_date_edit.setDate(date.today())
        dates_layout.addWidget(create_field_block("Quote Date", self._quote_date_edit))

        self._expiry_date_edit = QDateEdit(card)
        self._expiry_date_edit.setCalendarPopup(True)
        self._expiry_date_edit.setSpecialValueText("No expiry")
        self._expiry_date_edit.setMinimumDate(date(2000, 1, 1))
        self._expiry_date_edit.setDate(date.today())
        dates_layout.addWidget(create_field_block("Expiry Date (opt.)", self._expiry_date_edit))

        grid.addWidget(dates_row, 0, 1)

        # Row 1: Currency + Rate | Reference
        currency_row = QWidget(card)
        currency_layout = QHBoxLayout(currency_row)
        currency_layout.setContentsMargins(0, 0, 0, 0)
        currency_layout.setSpacing(10)

        self._currency_combo = SearchableComboBox(card)
        currency_layout.addWidget(create_field_block("Currency", self._currency_combo))

        self._exchange_rate_input = QLineEdit(card)
        self._exchange_rate_input.setPlaceholderText("Base currency")
        self._exchange_rate_input.setFixedWidth(120)
        self._exchange_rate_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._exchange_rate_input.setEnabled(False)
        currency_layout.addWidget(create_field_block("Rate", self._exchange_rate_input))

        grid.addWidget(currency_row, 1, 0)

        self._reference_input = QLineEdit(card)
        self._reference_input.setPlaceholderText("Optional reference or RFQ number")
        grid.addWidget(create_field_block("Reference", self._reference_input), 1, 1)

        # Row 2: Contract | Project
        self._contract_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Contract", self._contract_combo), 2, 0)

        self._project_combo = SearchableComboBox(card)
        grid.addWidget(create_field_block("Project", self._project_combo), 2, 1)

        # Row 3: Notes (full width)
        self._notes_input = QPlainTextEdit(card)
        self._notes_input.setMinimumHeight(64)
        self._notes_input.setMaximumHeight(96)
        self._notes_input.setPlaceholderText("Notes")
        grid.addWidget(create_field_block("Notes", self._notes_input), 3, 0, 1, 2)

        return card

    def _build_lines_section(self) -> QWidget:
        self._lines_grid = CustomerQuoteLinesGrid(self._service_registry, self._company_id, self)
        return self._lines_grid

    def _build_totals_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("InfoCard")

        outer = QHBoxLayout(panel)
        outer.setContentsMargins(14, 8, 14, 8)
        outer.setSpacing(10)

        self._line_count_label = QLabel("0 lines", panel)
        self._line_count_label.setObjectName("ToolbarMeta")
        outer.addWidget(self._line_count_label)
        outer.addStretch(1)

        totals = QGridLayout()
        totals.setSpacing(6)
        totals.setColumnMinimumWidth(1, 110)

        lbl_sub = QLabel("Subtotal", panel)
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        totals.addWidget(lbl_sub, 0, 0)
        self._subtotal_value = QLabel("0.00", panel)
        self._subtotal_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._subtotal_value.setObjectName("TotalsValue")
        totals.addWidget(self._subtotal_value, 0, 1)

        lbl_tax = QLabel("Tax", panel)
        lbl_tax.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        totals.addWidget(lbl_tax, 1, 0)
        self._tax_value = QLabel("0.00", panel)
        self._tax_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._tax_value.setObjectName("TotalsValue")
        totals.addWidget(self._tax_value, 1, 1)

        sep = QFrame(panel)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("TotalsSeparator")
        totals.addWidget(sep, 2, 0, 1, 2)

        lbl_total = QLabel("Total", panel)
        lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_total.setObjectName("CardTitle")
        totals.addWidget(lbl_total, 3, 0)
        self._total_value = QLabel("0.00", panel)
        self._total_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._total_value.setObjectName("TotalsGrandTotal")
        totals.addWidget(self._total_value, 3, 1)

        outer.addLayout(totals)
        return panel

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
                [(f"{c.contract_number} - {c.contract_title}", c.id) for c in contracts],
                placeholder="-- No contract --",
            )

            projects = self._service_registry.project_service.list_projects(self._company_id)
            self._project_combo.set_items(
                [(f"{p.project_code} - {p.project_name}", p.id) for p in projects],
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
            self._quote_date_edit.dateChanged.connect(self._on_data_changed)
            self._expiry_date_edit.dateChanged.connect(self._on_data_changed)
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

    def _load_quote(self) -> None:
        if self._quote_id is None:
            return
        try:
            detail = self._service_registry.customer_quote_service.get_quote(
                self._company_id, self._quote_id
            )
        except Exception:
            _log.warning("Quote form data load error", exc_info=True)
            return

        self._customer_combo.set_current_value(detail.customer_id)
        self._contract_combo.set_current_value(detail.contract_id)
        self._project_combo.set_current_value(detail.project_id)

        self._quote_date_edit.setDate(detail.quote_date)
        if detail.expiry_date is not None:
            self._expiry_date_edit.setDate(detail.expiry_date)

        self._currency_combo.set_current_value(detail.currency_code)

        if detail.exchange_rate is not None:
            self._exchange_rate_input.setText(str(detail.exchange_rate))

        self._reference_input.setText(detail.reference_number or "")
        self._notes_input.setPlainText(detail.notes or "")
        self._lines_grid.set_lines(detail.lines)

        self._on_currency_changed(self._currency_combo.current_value())
        self._update_totals()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_data_changed(self, *_args: object) -> None:
        self._update_totals()

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

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        customer_id = self._customer_combo.current_value()
        if not customer_id:
            self._show_error("Customer is required")
            return

        quote_date = self._quote_date_edit.date().toPython()
        expiry_date: date | None = self._expiry_date_edit.date().toPython()
        # Treat the special-value min date as "no expiry"
        if expiry_date == date(2000, 1, 1):
            expiry_date = None

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
            self._show_error("At least one quote line is required.")
            return

        try:
            if self._quote_id is None:
                cmd = CreateCustomerQuoteCommand(
                    customer_id=customer_id,
                    quote_date=quote_date,
                    expiry_date=expiry_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    reference_number=reference_number,
                    notes=notes,
                    contract_id=contract_id,
                    project_id=project_id,
                    lines=tuple(line_commands),
                )
                self._saved_quote = self._service_registry.customer_quote_service.create_draft_quote(
                    self._company_id, cmd
                )
            else:
                cmd_update = UpdateCustomerQuoteCommand(
                    customer_id=customer_id,
                    quote_date=quote_date,
                    expiry_date=expiry_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    reference_number=reference_number,
                    notes=notes,
                    contract_id=contract_id,
                    project_id=project_id,
                    lines=tuple(line_commands),
                )
                self._saved_quote = self._service_registry.customer_quote_service.update_draft_quote(
                    self._company_id, self._quote_id, cmd_update
                )
            self.accept()
        except (ValidationError, Exception) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()


# ---------------------------------------------------------------------------
# Conversion dialog
# ---------------------------------------------------------------------------


class ConvertQuoteDialog(QDialog):
    """Collect invoice date, due date, and optional overrides for quote conversion."""

    def __init__(
        self,
        quote_number: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Convert Quote to Invoice — {quote_number}")
        self.setModal(True)
        self.resize(440, 260)

        self._result: ConvertCustomerQuoteCommand | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        card = QFrame(self)
        card.setObjectName("PageCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._invoice_date_edit = QDateEdit(card)
        self._invoice_date_edit.setCalendarPopup(True)
        self._invoice_date_edit.setDate(date.today())
        grid.addWidget(create_field_block("Invoice Date", self._invoice_date_edit), 0, 0)

        self._due_date_edit = QDateEdit(card)
        self._due_date_edit.setCalendarPopup(True)
        self._due_date_edit.setDate(date.today())
        grid.addWidget(create_field_block("Due Date", self._due_date_edit), 0, 1)

        self._reference_input = QLineEdit(card)
        self._reference_input.setPlaceholderText("Optional invoice reference")
        grid.addWidget(create_field_block("Reference", self._reference_input), 1, 0, 1, 2)

        self._notes_input = QPlainTextEdit(card)
        self._notes_input.setMinimumHeight(56)
        self._notes_input.setMaximumHeight(80)
        self._notes_input.setPlaceholderText("Notes for invoice (optional)")
        grid.addWidget(create_field_block("Notes", self._notes_input), 2, 0, 1, 2)

        layout.addWidget(card)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self._handle_submit)
        button_box.rejected.connect(self.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("Convert to Invoice")
            ok_button.setProperty("variant", "primary")
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")
        layout.addWidget(button_box)

    @property
    def result_command(self) -> ConvertCustomerQuoteCommand | None:
        return self._result

    @classmethod
    def run_conversion(
        cls,
        quote_number: str,
        parent: QWidget | None = None,
    ) -> ConvertCustomerQuoteCommand | None:
        dialog = cls(quote_number, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.result_command
        return None

    def _handle_submit(self) -> None:
        invoice_date = self._invoice_date_edit.date().toPython()
        due_date = self._due_date_edit.date().toPython()
        reference_number = self._reference_input.text().strip() or None
        notes = self._notes_input.toPlainText().strip() or None

        self._result = ConvertCustomerQuoteCommand(
            invoice_date=invoice_date,
            due_date=due_date,
            reference_number=reference_number,
            notes=notes,
        )
        self.accept()
