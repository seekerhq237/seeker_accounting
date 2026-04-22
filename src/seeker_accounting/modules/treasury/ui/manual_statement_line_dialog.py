from __future__ import annotations

import logging

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.treasury.dto.bank_statement_commands import CreateManualStatementLineCommand
from seeker_accounting.modules.treasury.dto.bank_statement_dto import BankStatementLineDTO
from seeker_accounting.platform.exceptions import ValidationError

_log = logging.getLogger(__name__)


class ManualStatementLineDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._saved_line: BankStatementLineDTO | None = None

        self.setWindowTitle(f"Add Manual Statement Line — {company_name}")
        self.setModal(True)
        self.resize(500, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_form_section())

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
        layout.addWidget(self._button_box)

        self._load_reference_data()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.manual_statement_line")

    @property
    def saved_line(self) -> BankStatementLineDTO | None:
        return self._saved_line

    @classmethod
    def create_line(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> BankStatementLineDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_line
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_form_section(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self._account_combo = QComboBox(card)
        form.addRow("Financial Account", self._account_combo)

        self._line_date_edit = QDateEdit(card)
        self._line_date_edit.setCalendarPopup(True)
        self._line_date_edit.setDate(date.today())
        form.addRow("Date", self._line_date_edit)

        self._value_date_edit = QDateEdit(card)
        self._value_date_edit.setCalendarPopup(True)
        self._value_date_edit.setDate(date.today())
        form.addRow("Value Date", self._value_date_edit)

        self._description_input = QLineEdit(card)
        self._description_input.setPlaceholderText("Line description")
        form.addRow("Description", self._description_input)

        self._reference_input = QLineEdit(card)
        self._reference_input.setPlaceholderText("Optional reference")
        form.addRow("Reference", self._reference_input)

        self._debit_input = QLineEdit(card)
        self._debit_input.setPlaceholderText("0.00")
        form.addRow("Debit Amount", self._debit_input)

        self._credit_input = QLineEdit(card)
        self._credit_input.setPlaceholderText("0.00")
        form.addRow("Credit Amount", self._credit_input)

        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            accounts = self._service_registry.financial_account_service.list_financial_accounts(
                self._company_id, active_only=True
            )
            self._account_combo.clear()
            self._account_combo.addItem("-- Select account --", 0)
            for a in accounts:
                self._account_combo.addItem(f"{a.account_code} — {a.name}", a.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        financial_account_id = self._account_combo.currentData()
        if not financial_account_id or financial_account_id == 0:
            self._set_error("Please select a financial account.")
            return

        description = self._description_input.text().strip()
        if not description:
            self._set_error("Description is required.")
            return

        line_date = self._line_date_edit.date().toPython()
        value_date = self._value_date_edit.date().toPython()
        reference = self._reference_input.text().strip() or None
        debit_amount = self._parse_decimal(self._debit_input.text()) or Decimal("0.00")
        credit_amount = self._parse_decimal(self._credit_input.text()) or Decimal("0.00")

        if debit_amount == Decimal("0.00") and credit_amount == Decimal("0.00"):
            self._set_error("Either debit or credit amount must be greater than zero.")
            return

        try:
            cmd = CreateManualStatementLineCommand(
                financial_account_id=financial_account_id,
                line_date=line_date,
                description=description,
                debit_amount=debit_amount,
                credit_amount=credit_amount,
                value_date=value_date,
                reference=reference,
            )
            self._saved_line = self._service_registry.bank_statement_service.create_manual_statement_line(
                self._company_id, cmd
            )
            self.accept()
        except (ValidationError, Exception) as exc:
            self._set_error(str(exc))

    def _set_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _parse_decimal(self, text: str) -> Decimal | None:
        text = text.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
