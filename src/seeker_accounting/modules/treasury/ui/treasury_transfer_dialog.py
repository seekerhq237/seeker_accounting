from __future__ import annotations

import logging

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.treasury.dto.treasury_transfer_commands import (
    CreateTreasuryTransferCommand,
    UpdateTreasuryTransferCommand,
)
from seeker_accounting.modules.treasury.dto.treasury_transfer_dto import TreasuryTransferDetailDTO
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.searchable_combo_box import SearchableComboBox

_log = logging.getLogger(__name__)


class TreasuryTransferDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        transfer_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._transfer_id = transfer_id
        self._saved_transfer: TreasuryTransferDetailDTO | None = None

        is_edit = transfer_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Treasury Transfer — {company_name}")
        self.setModal(True)
        self.resize(650, 480)

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
        if is_edit:
            self._load_transfer()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.treasury_transfer")

    @property
    def saved_transfer(self) -> TreasuryTransferDetailDTO | None:
        return self._saved_transfer

    @classmethod
    def create_transfer(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> TreasuryTransferDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_transfer
        return None

    @classmethod
    def edit_transfer(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        transfer_id: int,
        parent: QWidget | None = None,
    ) -> TreasuryTransferDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, transfer_id=transfer_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_transfer
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

        self._from_account_combo = SearchableComboBox(card)
        form.addRow("From Account", self._from_account_combo)

        self._to_account_combo = SearchableComboBox(card)
        form.addRow("To Account", self._to_account_combo)

        self._transfer_date_edit = QDateEdit(card)
        self._transfer_date_edit.setCalendarPopup(True)
        self._transfer_date_edit.setDate(date.today())
        form.addRow("Transfer Date", self._transfer_date_edit)

        self._currency_combo = SearchableComboBox(card)
        form.addRow("Currency", self._currency_combo)

        self._exchange_rate_input = QLineEdit(card)
        self._exchange_rate_input.setPlaceholderText("Exchange rate")
        form.addRow("Exchange Rate", self._exchange_rate_input)

        self._amount_input = QLineEdit(card)
        self._amount_input.setPlaceholderText("0.00")
        form.addRow("Amount", self._amount_input)

        self._reference_input = QLineEdit(card)
        self._reference_input.setPlaceholderText("Optional reference")
        form.addRow("Reference", self._reference_input)

        self._description_input = QLineEdit(card)
        self._description_input.setPlaceholderText("Optional description")
        form.addRow("Description", self._description_input)

        self._notes_input = QPlainTextEdit(card)
        self._notes_input.setMaximumHeight(50)
        self._notes_input.setPlaceholderText("Notes")
        form.addRow("Notes", self._notes_input)

        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_reference_data(self) -> None:
        try:
            accounts = self._service_registry.financial_account_service.list_financial_accounts(
                self._company_id, active_only=True
            )
            account_items = [(f"{a.account_code} — {a.name}", a.id) for a in accounts]
            self._from_account_combo.set_items(
                account_items,
                placeholder="-- Select account --",
                placeholder_value=0,
            )
            self._to_account_combo.set_items(
                account_items,
                placeholder="-- Select account --",
                placeholder_value=0,
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        try:
            ref = self._service_registry.reference_data_service.list_active_currencies()
            self._currency_combo.set_items(
                [(cur.code, cur.code) for cur in ref],
                placeholder="-- Select currency --",
            )
            ctx = self._service_registry.active_company_context
            if ctx.base_currency_code:
                self._currency_combo.set_current_value(ctx.base_currency_code)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_transfer(self) -> None:
        if self._transfer_id is None:
            return
        try:
            detail = self._service_registry.treasury_transfer_service.get_treasury_transfer(
                self._company_id, self._transfer_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._from_account_combo.set_current_value(detail.from_financial_account_id)
        self._to_account_combo.set_current_value(detail.to_financial_account_id)

        self._transfer_date_edit.setDate(detail.transfer_date)

        self._currency_combo.set_current_value(detail.currency_code)

        if detail.exchange_rate is not None:
            self._exchange_rate_input.setText(str(detail.exchange_rate))

        self._amount_input.setText(str(detail.amount))
        self._reference_input.setText(detail.reference_number or "")
        self._description_input.setText(detail.description or "")
        self._notes_input.setPlainText(detail.notes or "")

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        from_financial_account_id = self._from_account_combo.current_value()
        if not from_financial_account_id or from_financial_account_id == 0:
            self._set_error("Please select a 'From Account'.")
            return

        to_financial_account_id = self._to_account_combo.current_value()
        if not to_financial_account_id or to_financial_account_id == 0:
            self._set_error("Please select a 'To Account'.")
            return

        if from_financial_account_id == to_financial_account_id:
            self._set_error("'From Account' and 'To Account' must be different.")
            return

        transfer_date = self._transfer_date_edit.date().toPython()
        currency_code = self._currency_combo.current_value() or ""
        exchange_rate = self._parse_decimal(self._exchange_rate_input.text())
        amount = self._parse_decimal(self._amount_input.text()) or Decimal("0")
        reference_number = self._reference_input.text().strip() or None
        description = self._description_input.text().strip() or None
        notes = self._notes_input.toPlainText().strip() or None

        try:
            if self._transfer_id is None:
                cmd = CreateTreasuryTransferCommand(
                    from_financial_account_id=from_financial_account_id,
                    to_financial_account_id=to_financial_account_id,
                    transfer_date=transfer_date,
                    currency_code=currency_code,
                    amount=amount,
                    reference_number=reference_number,
                    description=description,
                    notes=notes,
                    exchange_rate=exchange_rate,
                )
                self._saved_transfer = self._service_registry.treasury_transfer_service.create_draft_transfer(
                    self._company_id, cmd
                )
            else:
                cmd_update = UpdateTreasuryTransferCommand(
                    from_financial_account_id=from_financial_account_id,
                    to_financial_account_id=to_financial_account_id,
                    transfer_date=transfer_date,
                    currency_code=currency_code,
                    amount=amount,
                    reference_number=reference_number,
                    description=description,
                    notes=notes,
                    exchange_rate=exchange_rate,
                )
                self._saved_transfer = self._service_registry.treasury_transfer_service.update_draft_transfer(
                    self._company_id, self._transfer_id, cmd_update
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
