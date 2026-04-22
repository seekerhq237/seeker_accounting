from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from seeker_accounting.modules.treasury.dto.financial_account_commands import (
    CreateFinancialAccountCommand,
    UpdateFinancialAccountCommand,
)
from seeker_accounting.modules.treasury.dto.financial_account_dto import FinancialAccountDetailDTO
from seeker_accounting.platform.exceptions import ValidationError

_log = logging.getLogger(__name__)


class FinancialAccountDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        account_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._company_id = company_id
        self._account_id = account_id
        self._saved_account: FinancialAccountDetailDTO | None = None

        is_edit = account_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Financial Account — {company_name}")
        self.setModal(True)
        self.resize(600, 450)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_form(is_edit))

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
            self._load_account()
        else:
            self._suggest_code()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.financial_account")

    @property
    def saved_account(self) -> FinancialAccountDetailDTO | None:
        return self._saved_account

    @classmethod
    def create_account(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> FinancialAccountDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_account
        return None

    @classmethod
    def edit_account(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        account_id: int,
        parent: QWidget | None = None,
    ) -> FinancialAccountDetailDTO | None:
        dialog = cls(service_registry, company_id, company_name, account_id=account_id, parent=parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.saved_account
        return None

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_form(self, is_edit: bool) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)

        self._account_code_input = QLineEdit(card)
        self._account_code_input.setPlaceholderText("e.g. BANK-001")
        form.addRow("Account Code", self._account_code_input)

        self._name_input = QLineEdit(card)
        self._name_input.setPlaceholderText("e.g. Main Operating Account")
        form.addRow("Name", self._name_input)

        self._type_combo = QComboBox(card)
        self._type_combo.addItem("Bank", "bank")
        self._type_combo.addItem("Cash", "cash")
        self._type_combo.addItem("Petty Cash", "petty_cash")
        form.addRow("Type", self._type_combo)

        self._gl_account_combo = QComboBox(card)
        form.addRow("GL Account", self._gl_account_combo)

        self._currency_combo = QComboBox(card)
        form.addRow("Currency", self._currency_combo)

        self._bank_name_input = QLineEdit(card)
        self._bank_name_input.setPlaceholderText("Optional")
        form.addRow("Bank Name", self._bank_name_input)

        self._bank_account_number_input = QLineEdit(card)
        self._bank_account_number_input.setPlaceholderText("Optional")
        form.addRow("Bank Account Number", self._bank_account_number_input)

        self._bank_branch_input = QLineEdit(card)
        self._bank_branch_input.setPlaceholderText("Optional")
        form.addRow("Bank Branch", self._bank_branch_input)

        self._is_active_checkbox: QCheckBox | None = None
        if is_edit:
            self._is_active_checkbox = QCheckBox("Active", card)
            self._is_active_checkbox.setChecked(True)
            form.addRow("Status", self._is_active_checkbox)

        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _suggest_code(self) -> None:
        try:
            code = self._service_registry.code_suggestion_service.suggest("financial_account", self._company_id)
            self._account_code_input.setText(code)
        except Exception:
            pass

    def _load_reference_data(self) -> None:
        try:
            gl_accounts = self._service_registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
            self._gl_account_combo.clear()
            self._gl_account_combo.addItem("-- Select GL account --", 0)
            for a in gl_accounts:
                self._gl_account_combo.addItem(f"{a.account_code} — {a.account_name}", a.id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

        try:
            currencies = self._service_registry.reference_data_service.list_active_currencies()
            self._currency_combo.clear()
            for cur in currencies:
                self._currency_combo.addItem(cur.code, cur.code)
            ctx = self._service_registry.active_company_context
            if ctx.base_currency_code:
                idx = self._currency_combo.findData(ctx.base_currency_code)
                if idx >= 0:
                    self._currency_combo.setCurrentIndex(idx)
        except Exception:
            _log.warning("Form data load error", exc_info=True)

    def _load_account(self) -> None:
        if self._account_id is None:
            return
        try:
            detail = self._service_registry.financial_account_service.get_financial_account(
                self._company_id, self._account_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._account_code_input.setText(detail.account_code)
        self._name_input.setText(detail.name)

        type_idx = self._type_combo.findData(detail.financial_account_type_code)
        if type_idx >= 0:
            self._type_combo.setCurrentIndex(type_idx)

        gl_idx = self._gl_account_combo.findData(detail.gl_account_id)
        if gl_idx >= 0:
            self._gl_account_combo.setCurrentIndex(gl_idx)

        cur_idx = self._currency_combo.findData(detail.currency_code)
        if cur_idx >= 0:
            self._currency_combo.setCurrentIndex(cur_idx)

        self._bank_name_input.setText(detail.bank_name or "")
        self._bank_account_number_input.setText(detail.bank_account_number or "")
        self._bank_branch_input.setText(detail.bank_branch or "")

        if self._is_active_checkbox is not None:
            self._is_active_checkbox.setChecked(detail.is_active)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _handle_submit(self) -> None:
        self._error_label.hide()

        account_code = self._account_code_input.text().strip()
        if not account_code:
            self._set_error("Account code is required.")
            return

        name = self._name_input.text().strip()
        if not name:
            self._set_error("Name is required.")
            return

        financial_account_type_code = self._type_combo.currentData() or ""

        gl_account_id = self._gl_account_combo.currentData()
        if not gl_account_id or gl_account_id == 0:
            self._set_error("Please select a GL account.")
            return

        currency_code = self._currency_combo.currentData() or ""
        if not currency_code:
            self._set_error("Please select a currency.")
            return

        bank_name = self._bank_name_input.text().strip() or None
        bank_account_number = self._bank_account_number_input.text().strip() or None
        bank_branch = self._bank_branch_input.text().strip() or None

        try:
            if self._account_id is None:
                cmd = CreateFinancialAccountCommand(
                    account_code=account_code,
                    name=name,
                    financial_account_type_code=financial_account_type_code,
                    gl_account_id=gl_account_id,
                    currency_code=currency_code,
                    bank_name=bank_name,
                    bank_account_number=bank_account_number,
                    bank_branch=bank_branch,
                )
                self._saved_account = self._service_registry.financial_account_service.create_financial_account(
                    self._company_id, cmd
                )
            else:
                is_active = self._is_active_checkbox.isChecked() if self._is_active_checkbox is not None else True
                cmd_update = UpdateFinancialAccountCommand(
                    account_code=account_code,
                    name=name,
                    financial_account_type_code=financial_account_type_code,
                    gl_account_id=gl_account_id,
                    currency_code=currency_code,
                    bank_name=bank_name,
                    bank_account_number=bank_account_number,
                    bank_branch=bank_branch,
                    is_active=is_active,
                )
                self._saved_account = self._service_registry.financial_account_service.update_financial_account(
                    self._company_id, self._account_id, cmd_update
                )
            self.accept()
        except (ValidationError, Exception) as exc:
            self._set_error(str(exc))

    def _set_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
