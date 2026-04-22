from __future__ import annotations

import logging

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.sales.dto.customer_receipt_commands import (
    CreateCustomerReceiptCommand,
    UpdateCustomerReceiptCommand,
)
from seeker_accounting.modules.sales.dto.customer_receipt_dto import CustomerReceiptDetailDTO
from seeker_accounting.modules.sales.ui.customer_receipt_allocations_panel import CustomerReceiptAllocationsPanel
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class CustomerReceiptDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        receipt_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._receipt_id = receipt_id
        self._saved_receipt: CustomerReceiptDetailDTO | None = None

        is_edit = receipt_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Customer Receipt - {company_name}")
        self.setModal(True)
        self.resize(920, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_header_section())
        layout.addWidget(self._build_allocations_section(), 1)
        layout.addWidget(self._build_summary_panel())

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
            save_button.setText("Create Receipt" if not is_edit else "Save Changes")
            save_button.setProperty("variant", "primary")
        cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")
        layout.addWidget(self._button_box)

        self._load_reference_data()
        if is_edit:
            self._load_receipt()

        from seeker_accounting.shared.ui.help_button import install_help_button

        install_help_button(self, "dialog.customer_receipt")

    @property
    def saved_receipt(self) -> CustomerReceiptDetailDTO | None:
        return self._saved_receipt

    @classmethod
    def create_receipt(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> CustomerReceiptDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_receipt
        return None

    @classmethod
    def edit_receipt(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        receipt_id: int,
        parent: QWidget | None = None,
    ) -> CustomerReceiptDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, receipt_id=receipt_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_receipt
        return None

    def _build_header_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        summary = QLabel(
            "Record what was received, then allocate it across open invoices if needed.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        form.addRow(summary)

        self._customer_combo = SearchableComboBox(card)
        form.addRow("Customer", self._customer_combo)

        self._financial_account_combo = SearchableComboBox(card)
        form.addRow("Financial Account", self._financial_account_combo)

        date_row = QWidget(card)
        date_layout = QHBoxLayout(date_row)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(12)

        self._receipt_date_edit = QDateEdit(card)
        self._receipt_date_edit.setCalendarPopup(True)
        self._receipt_date_edit.setDate(date.today())
        date_layout.addWidget(QLabel("Receipt date"))
        date_layout.addWidget(self._receipt_date_edit)
        date_layout.addStretch(1)

        form.addRow(date_row)

        currency_row = QWidget(card)
        currency_layout = QHBoxLayout(currency_row)
        currency_layout.setContentsMargins(0, 0, 0, 0)
        currency_layout.setSpacing(12)

        self._currency_combo = SearchableComboBox(card)
        currency_layout.addWidget(QLabel("Currency"))
        currency_layout.addWidget(self._currency_combo)

        self._exchange_rate_input = QLineEdit(card)
        self._exchange_rate_input.setPlaceholderText("Base currency")
        self._exchange_rate_input.setFixedWidth(120)
        self._exchange_rate_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._exchange_rate_input.setEnabled(False)
        currency_layout.addWidget(QLabel("Rate"))
        currency_layout.addWidget(self._exchange_rate_input)
        currency_layout.addStretch(1)

        form.addRow(currency_row)

        self._amount_input = QLineEdit(card)
        self._amount_input.setPlaceholderText("0.00")
        self._amount_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Amount Received", self._amount_input)

        self._reference_input = QLineEdit(card)
        self._reference_input.setPlaceholderText("Optional reference")
        form.addRow("Reference", self._reference_input)

        self._notes_input = QPlainTextEdit(card)
        self._notes_input.setMaximumHeight(50)
        self._notes_input.setPlaceholderText("Notes")
        form.addRow("Notes", self._notes_input)

        return card

    def _build_allocations_section(self) -> QWidget:
        self._allocations_panel = CustomerReceiptAllocationsPanel(
            self._service_registry, self._company_id, self
        )
        return self._allocations_panel

    def _build_summary_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("InfoCard")

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(24)

        self._amount_received_label = QLabel("Received: 0.00", panel)
        layout.addWidget(self._amount_received_label)

        self._total_allocated_label = QLabel("Allocated: 0.00", panel)
        layout.addWidget(self._total_allocated_label)

        self._remaining_label = QLabel("Remaining: 0.00", panel)
        self._remaining_label.setObjectName("CardTitle")
        layout.addWidget(self._remaining_label)

        layout.addStretch(1)
        return panel

    def _load_reference_data(self) -> None:
        try:
            customers = self._service_registry.customer_service.list_customers(
                self._company_id, active_only=True
            )
            self._customer_combo.set_items(
                [(f"{c.customer_code} - {c.display_name}", c.id) for c in customers],
                placeholder="-- Select customer --",
                placeholder_value=0,
                search_texts=[f"{c.customer_code} {c.display_name}" for c in customers],
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        try:
            accounts = self._service_registry.financial_account_service.list_financial_accounts(
                self._company_id, active_only=True
            )
            self._financial_account_combo.set_items(
                [(f"{a.account_code} - {a.name}", a.id) for a in accounts],
                placeholder="-- Select account --",
                placeholder_value=0,
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        try:
            currencies = self._service_registry.reference_data_service.list_active_currencies()
            self._currency_combo.set_items(
                [(cur.code, cur.code) for cur in currencies],
                placeholder="-- Select currency --",
            )
            base_currency_code = self._base_currency_code()
            if base_currency_code:
                self._currency_combo.set_current_value(base_currency_code)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        self._customer_combo.value_changed.connect(self._on_customer_changed)
        self._financial_account_combo.value_changed.connect(self._refresh_preview)
        self._receipt_date_edit.dateChanged.connect(self._refresh_preview)
        self._currency_combo.value_changed.connect(self._on_currency_changed)
        self._exchange_rate_input.textChanged.connect(self._refresh_preview)
        self._amount_input.textChanged.connect(self._refresh_preview)
        self._reference_input.textChanged.connect(self._refresh_preview)
        self._notes_input.textChanged.connect(self._refresh_preview)
        self._allocations_panel.allocations_changed.connect(self._refresh_preview)
        self._on_currency_changed(self._currency_combo.current_value())

    def _load_receipt(self) -> None:
        if self._receipt_id is None:
            return
        try:
            detail = self._service_registry.customer_receipt_service.get_customer_receipt(
                self._company_id, self._receipt_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._customer_combo.set_current_value(detail.customer_id)
        self._financial_account_combo.set_current_value(detail.financial_account_id)
        self._receipt_date_edit.setDate(detail.receipt_date)
        self._currency_combo.set_current_value(detail.currency_code)

        if detail.exchange_rate is not None:
            self._exchange_rate_input.setText(str(detail.exchange_rate))

        self._amount_input.setText(str(detail.amount_received))
        self._reference_input.setText(detail.reference_number or "")
        self._notes_input.setPlainText(detail.notes or "")
        self._allocations_panel.set_allocations(
            customer_id=detail.customer_id,
            existing_allocations=detail.allocations,
        )
        self._on_currency_changed(self._currency_combo.current_value())
        self._refresh_preview()

    def _on_customer_changed(self, _value: object) -> None:
        customer_id = self._customer_combo.current_value()
        if customer_id and customer_id > 0:
            self._allocations_panel.load_open_invoices(customer_id)
        else:
            self._allocations_panel.clear()
        self._refresh_preview()

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

        self._refresh_preview()

    def _refresh_preview(self, *_args: object) -> None:
        amount_received = self._parse_decimal(self._amount_input.text()) or Decimal("0.00")
        allocated = self._allocations_panel.entered_total()
        remaining = amount_received - allocated

        self._amount_received_label.setText(f"Received: {amount_received:,.2f}")
        self._total_allocated_label.setText(f"Allocated: {allocated:,.2f}")
        if remaining >= Decimal("0.00"):
            self._remaining_label.setText(f"Remaining: {remaining:,.2f}")
        else:
            self._remaining_label.setText(f"Over allocated: {abs(remaining):,.2f}")

    def _handle_submit(self) -> None:
        self._error_label.hide()

        customer_id = self._customer_combo.current_value()
        if not customer_id or customer_id == 0:
            self._set_error("Please select a customer.")
            return

        financial_account_id = self._financial_account_combo.current_value()
        if not financial_account_id or financial_account_id == 0:
            self._set_error("Please select a financial account.")
            return

        receipt_date = self._receipt_date_edit.date().toPython()
        currency_code = self._currency_combo.current_value() or ""
        if not currency_code:
            self._set_error("Please select a currency.")
            return

        exchange_rate_text = self._exchange_rate_input.text().strip()
        exchange_rate = self._parse_decimal(exchange_rate_text)
        if exchange_rate_text and exchange_rate is None:
            self._set_error("Exchange rate must be a valid number.")
            return

        amount_text = self._amount_input.text().strip()
        amount_received = self._parse_decimal(amount_text)
        if amount_text and amount_received is None:
            self._set_error("Amount received must be a valid number.")
            return

        reference_number = self._reference_input.text().strip() or None
        notes = self._notes_input.toPlainText().strip() or None
        allocation_commands = self._allocations_panel.get_allocation_commands()

        try:
            if self._receipt_id is None:
                cmd = CreateCustomerReceiptCommand(
                    customer_id=customer_id,
                    financial_account_id=financial_account_id,
                    receipt_date=receipt_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    amount_received=amount_received or Decimal("0"),
                    reference_number=reference_number,
                    notes=notes,
                    allocations=tuple(allocation_commands),
                )
                self._saved_receipt = self._service_registry.customer_receipt_service.create_draft_receipt(
                    self._company_id, cmd
                )
            else:
                cmd_update = UpdateCustomerReceiptCommand(
                    customer_id=customer_id,
                    financial_account_id=financial_account_id,
                    receipt_date=receipt_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    amount_received=amount_received or Decimal("0"),
                    reference_number=reference_number,
                    notes=notes,
                    allocations=tuple(allocation_commands),
                )
                self._saved_receipt = self._service_registry.customer_receipt_service.update_draft_receipt(
                    self._company_id, self._receipt_id, cmd_update
                )
            self.accept()
        except (ValidationError, Exception) as exc:
            self._set_error(str(exc))

    def _set_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _parse_decimal(self, text: str) -> Decimal | None:
        text = text.replace(",", "").strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None

    def _base_currency_code(self) -> str | None:
        return getattr(self._service_registry.active_company_context, "base_currency_code", None)
