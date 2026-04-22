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
from seeker_accounting.modules.payroll.dto.payroll_component_dto import (
    CreatePayrollComponentCommand,
    UpdatePayrollComponentCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError

_log = logging.getLogger(__name__)

_COMPONENT_TYPES = [
    ("earning",               "Earning"),
    ("deduction",             "Deduction"),
    ("employer_contribution", "Employer Contribution"),
    ("tax",                   "Tax"),
    ("informational",         "Informational"),
]

_CALC_METHODS = [
    ("fixed_amount", "Fixed Amount"),
    ("percentage",   "Percentage"),
    ("rule_based",   "Rule Based"),
    ("manual_input", "Manual Input"),
    ("hourly",       "Hourly"),
]


class PayrollComponentFormDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        component_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._company_id = company_id
        self._component_id = component_id

        is_edit = component_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Payroll Component — {company_name}")
        self.setModal(True)
        self.resize(500, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Component definition ──────────────────────────────────────────────
        def_card = QFrame(self)
        def_card.setObjectName("PageCard")
        def_form = QFormLayout(def_card)
        def_form.setContentsMargins(18, 16, 18, 16)
        def_form.setSpacing(10)
        def_hdr = QLabel("Component Definition", def_card)
        def_hdr.setObjectName("CardTitle")
        def_form.addRow(def_hdr)

        self._code_input = QLineEdit(def_card)
        self._code_input.setPlaceholderText("e.g. BASE_SALARY")
        self._code_input.setMaxLength(30)
        def_form.addRow("Code *", self._code_input)

        self._name_input = QLineEdit(def_card)
        self._name_input.setPlaceholderText("Component name")
        self._name_input.setMaxLength(100)
        def_form.addRow("Name *", self._name_input)

        self._type_combo = QComboBox(def_card)
        for code, label in _COMPONENT_TYPES:
            self._type_combo.addItem(label, code)
        def_form.addRow("Component Type *", self._type_combo)

        self._method_combo = QComboBox(def_card)
        for code, label in _CALC_METHODS:
            self._method_combo.addItem(label, code)
        def_form.addRow("Calculation Method *", self._method_combo)

        self._taxable_cb = QCheckBox("Taxable", def_card)
        def_form.addRow("", self._taxable_cb)

        self._pensionable_cb = QCheckBox("Pensionable", def_card)
        def_form.addRow("", self._pensionable_cb)

        if is_edit:
            self._active_cb = QCheckBox("Active", def_card)
            self._active_cb.setChecked(True)
            def_form.addRow("Status", self._active_cb)

        layout.addWidget(def_card)

        # ── Account mapping ───────────────────────────────────────────────────
        acct_card = QFrame(self)
        acct_card.setObjectName("PageCard")
        acct_form = QFormLayout(acct_card)
        acct_form.setContentsMargins(18, 16, 18, 16)
        acct_form.setSpacing(10)
        acct_hdr = QLabel("Account Mapping (optional)", acct_card)
        acct_hdr.setObjectName("CardTitle")
        acct_form.addRow(acct_hdr)

        self._expense_acct_combo = QComboBox(acct_card)
        acct_form.addRow("Expense Account", self._expense_acct_combo)

        self._liability_acct_combo = QComboBox(acct_card)
        acct_form.addRow("Liability Account", self._liability_acct_combo)

        layout.addWidget(acct_card)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_accounts()
        if is_edit:
            self._load_existing()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_component_form", dialog=True)

    def _load_accounts(self) -> None:
        try:
            accounts = self._sr.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
        except Exception:
            accounts = []
        for combo in (self._expense_acct_combo, self._liability_acct_combo):
            combo.clear()
            combo.addItem("— None —", None)
            for acct in accounts:
                combo.addItem(f"{acct.account_code} — {acct.account_name}", acct.id)

    def _load_existing(self) -> None:
        if self._component_id is None:
            return
        try:
            comp = self._sr.payroll_component_service.get_component(
                self._company_id, self._component_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._code_input.setText(comp.component_code)
        self._name_input.setText(comp.component_name)
        self._set_combo_value(self._type_combo, comp.component_type_code)
        self._set_combo_value(self._method_combo, comp.calculation_method_code)
        self._taxable_cb.setChecked(comp.is_taxable)
        self._pensionable_cb.setChecked(comp.is_pensionable)
        self._set_combo_value_int(self._expense_acct_combo, comp.expense_account_id)
        self._set_combo_value_int(self._liability_acct_combo, comp.liability_account_id)
        if hasattr(self, "_active_cb"):
            self._active_cb.setChecked(comp.is_active)

    def _set_combo_value(self, combo: QComboBox, value: str | None) -> None:
        if value is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _set_combo_value_int(self, combo: QComboBox, value: int | None) -> None:
        if value is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _submit(self) -> None:
        self._error_label.hide()
        code = self._code_input.text().strip()
        name = self._name_input.text().strip()
        type_code = self._type_combo.currentData()
        method_code = self._method_combo.currentData()
        is_taxable = self._taxable_cb.isChecked()
        is_pensionable = self._pensionable_cb.isChecked()
        expense_acct = self._expense_acct_combo.currentData()
        liability_acct = self._liability_acct_combo.currentData()
        is_active = self._active_cb.isChecked() if hasattr(self, "_active_cb") else True

        try:
            if self._component_id is None:
                self._sr.payroll_component_service.create_component(
                    self._company_id,
                    CreatePayrollComponentCommand(
                        component_code=code,
                        component_name=name,
                        component_type_code=type_code,
                        calculation_method_code=method_code,
                        is_taxable=is_taxable,
                        is_pensionable=is_pensionable,
                        expense_account_id=expense_acct,
                        liability_account_id=liability_acct,
                    ),
                )
            else:
                self._sr.payroll_component_service.update_component(
                    self._company_id,
                    self._component_id,
                    UpdatePayrollComponentCommand(
                        component_code=code,
                        component_name=name,
                        component_type_code=type_code,
                        calculation_method_code=method_code,
                        is_taxable=is_taxable,
                        is_pensionable=is_pensionable,
                        is_active=is_active,
                        expense_account_id=expense_acct,
                        liability_account_id=liability_acct,
                    ),
                )
            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
