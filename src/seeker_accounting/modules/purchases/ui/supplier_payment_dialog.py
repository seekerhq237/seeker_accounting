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
from seeker_accounting.modules.purchases.dto.supplier_payment_commands import (
    CreateSupplierPaymentCommand,
    UpdateSupplierPaymentCommand,
)
from seeker_accounting.modules.purchases.dto.supplier_payment_dto import SupplierPaymentDetailDTO
from seeker_accounting.modules.purchases.ui.supplier_payment_allocations_panel import (
    SupplierPaymentAllocationsPanel,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class SupplierPaymentDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        payment_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._payment_id = payment_id
        self._saved_payment: SupplierPaymentDetailDTO | None = None

        is_edit = payment_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Supplier Payment - {company_name}")
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
            save_button.setText("Create Payment" if not is_edit else "Save Changes")
            save_button.setProperty("variant", "primary")
        cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setProperty("variant", "secondary")
        layout.addWidget(self._button_box)

        self._load_reference_data()
        if is_edit:
            self._load_payment()

        from seeker_accounting.shared.ui.help_button import install_help_button

        install_help_button(self, "dialog.supplier_payment")

    @property
    def saved_payment(self) -> SupplierPaymentDetailDTO | None:
        return self._saved_payment

    @classmethod
    def create_payment(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> SupplierPaymentDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_payment
        return None

    @classmethod
    def edit_payment(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        payment_id: int,
        parent: QWidget | None = None,
    ) -> SupplierPaymentDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, payment_id=payment_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_payment
        return None

    def _build_header_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        summary = QLabel(
            "Record what was paid, then allocate it across open supplier bills if needed.",
            card,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        form.addRow(summary)

        self._supplier_combo = SearchableComboBox(card)
        form.addRow("Supplier", self._supplier_combo)

        self._financial_account_combo = SearchableComboBox(card)
        form.addRow("Financial Account", self._financial_account_combo)

        date_row = QWidget(card)
        date_layout = QHBoxLayout(date_row)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(12)

        self._payment_date_edit = QDateEdit(card)
        self._payment_date_edit.setCalendarPopup(True)
        self._payment_date_edit.setDate(date.today())
        date_layout.addWidget(QLabel("Payment date"))
        date_layout.addWidget(self._payment_date_edit)
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
        form.addRow("Amount Paid", self._amount_input)

        self._reference_input = QLineEdit(card)
        self._reference_input.setPlaceholderText("Optional reference")
        form.addRow("Reference", self._reference_input)

        self._notes_input = QPlainTextEdit(card)
        self._notes_input.setMaximumHeight(50)
        self._notes_input.setPlaceholderText("Notes")
        form.addRow("Notes", self._notes_input)

        return card

    def _build_allocations_section(self) -> QWidget:
        self._allocations_panel = SupplierPaymentAllocationsPanel(
            self._service_registry, self._company_id, self
        )
        return self._allocations_panel

    def _build_summary_panel(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("InfoCard")

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(24)

        self._amount_paid_label = QLabel("Paid: 0.00", panel)
        layout.addWidget(self._amount_paid_label)

        self._total_allocated_label = QLabel("Allocated: 0.00", panel)
        layout.addWidget(self._total_allocated_label)

        self._remaining_label = QLabel("Remaining: 0.00", panel)
        self._remaining_label.setObjectName("CardTitle")
        layout.addWidget(self._remaining_label)

        layout.addStretch(1)
        return panel

    def _load_reference_data(self) -> None:
        try:
            suppliers = self._service_registry.supplier_service.list_suppliers(
                self._company_id, active_only=True
            )
            self._supplier_combo.set_items(
                [(f"{s.supplier_code} - {s.display_name}", s.id) for s in suppliers],
                placeholder="-- Select supplier --",
                placeholder_value=0,
                search_texts=[f"{s.supplier_code} {s.display_name}" for s in suppliers],
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

        self._supplier_combo.value_changed.connect(self._on_supplier_changed)
        self._financial_account_combo.value_changed.connect(self._refresh_preview)
        self._payment_date_edit.dateChanged.connect(self._refresh_preview)
        self._currency_combo.value_changed.connect(self._on_currency_changed)
        self._exchange_rate_input.textChanged.connect(self._refresh_preview)
        self._amount_input.textChanged.connect(self._refresh_preview)
        self._reference_input.textChanged.connect(self._refresh_preview)
        self._notes_input.textChanged.connect(self._refresh_preview)
        self._allocations_panel.allocations_changed.connect(self._refresh_preview)
        self._on_currency_changed(self._currency_combo.current_value())

    def _load_payment(self) -> None:
        if self._payment_id is None:
            return
        try:
            detail = self._service_registry.supplier_payment_service.get_supplier_payment(
                self._company_id, self._payment_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._supplier_combo.set_current_value(detail.supplier_id)
        self._financial_account_combo.set_current_value(detail.financial_account_id)
        self._payment_date_edit.setDate(detail.payment_date)
        self._currency_combo.set_current_value(detail.currency_code)

        if detail.exchange_rate is not None:
            self._exchange_rate_input.setText(str(detail.exchange_rate))

        self._amount_input.setText(str(detail.amount_paid))
        self._reference_input.setText(detail.reference_number or "")
        self._notes_input.setPlainText(detail.notes or "")
        self._allocations_panel.set_allocations(
            supplier_id=detail.supplier_id,
            existing_allocations=detail.allocations,
        )
        self._on_currency_changed(self._currency_combo.current_value())
        self._refresh_preview()

    def _on_supplier_changed(self, _value: object) -> None:
        supplier_id = self._supplier_combo.current_value()
        if supplier_id and supplier_id > 0:
            self._allocations_panel.load_open_bills(supplier_id)
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
        amount_paid = self._parse_decimal(self._amount_input.text()) or Decimal("0.00")
        allocated = self._allocations_panel.entered_total()
        remaining = amount_paid - allocated

        self._amount_paid_label.setText(f"Paid: {amount_paid:,.2f}")
        self._total_allocated_label.setText(f"Allocated: {allocated:,.2f}")
        if remaining >= Decimal("0.00"):
            self._remaining_label.setText(f"Remaining: {remaining:,.2f}")
        else:
            self._remaining_label.setText(f"Over allocated: {abs(remaining):,.2f}")

    def _handle_submit(self) -> None:
        self._error_label.hide()

        supplier_id = self._supplier_combo.current_value()
        if not supplier_id or supplier_id == 0:
            self._set_error("Please select a supplier.")
            return

        financial_account_id = self._financial_account_combo.current_value()
        if not financial_account_id or financial_account_id == 0:
            self._set_error("Please select a financial account.")
            return

        payment_date = self._payment_date_edit.date().toPython()
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
        amount_paid = self._parse_decimal(amount_text)
        if amount_text and amount_paid is None:
            self._set_error("Amount paid must be a valid number.")
            return

        reference_number = self._reference_input.text().strip() or None
        notes = self._notes_input.toPlainText().strip() or None
        allocation_commands = self._allocations_panel.get_allocation_commands()

        try:
            if self._payment_id is None:
                cmd = CreateSupplierPaymentCommand(
                    supplier_id=supplier_id,
                    financial_account_id=financial_account_id,
                    payment_date=payment_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    amount_paid=amount_paid or Decimal("0"),
                    reference_number=reference_number,
                    notes=notes,
                    allocations=tuple(allocation_commands),
                )
                self._saved_payment = self._service_registry.supplier_payment_service.create_draft_payment(
                    self._company_id, cmd
                )
            else:
                cmd_update = UpdateSupplierPaymentCommand(
                    supplier_id=supplier_id,
                    financial_account_id=financial_account_id,
                    payment_date=payment_date,
                    currency_code=currency_code,
                    exchange_rate=exchange_rate,
                    amount_paid=amount_paid or Decimal("0"),
                    reference_number=reference_number,
                    notes=notes,
                    allocations=tuple(allocation_commands),
                )
                self._saved_payment = self._service_registry.supplier_payment_service.update_draft_payment(
                    self._company_id, self._payment_id, cmd_update
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
