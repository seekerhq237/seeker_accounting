from __future__ import annotations

import logging

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
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
from seeker_accounting.modules.payroll.dto.payroll_rule_dto import (
    CreatePayrollRuleSetCommand,
    UpdatePayrollRuleSetCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError

_log = logging.getLogger(__name__)

_RULE_TYPES = [
    ("pit",              "PIT (IRPP Withholding)"),
    ("pension_employee", "Pension — Employee"),
    ("pension_employer", "Pension — Employer"),
    ("accident_risk",    "Accident Risk (CNPS)"),
    ("overtime",         "Overtime"),
    ("levy",             "Levy (TDL / other)"),
    ("other",            "Other"),
]

_CALC_BASES = [
    ("gross_salary",       "Gross Salary"),
    ("basic_salary",       "Basic Salary"),
    ("taxable_gross",      "Taxable Gross"),
    ("pensionable_gross",  "Pensionable Gross"),
    ("fixed",              "Fixed Amount"),
    ("other",              "Other"),
]


class PayrollRuleSetFormDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        rule_set_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._company_id = company_id
        self._rule_set_id = rule_set_id

        is_edit = rule_set_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Payroll Rule Set — {company_name}")
        self.setModal(True)
        self.resize(480, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        card = QFrame(self)
        card.setObjectName("PageCard")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(10)
        hdr = QLabel("Rule Set Definition", card)
        hdr.setObjectName("CardTitle")
        form.addRow(hdr)

        self._code_input = QLineEdit(card)
        self._code_input.setPlaceholderText("e.g. DGI_WITHHOLDING_BAREME")
        self._code_input.setMaxLength(30)
        form.addRow("Rule Code *", self._code_input)

        self._name_input = QLineEdit(card)
        self._name_input.setMaxLength(100)
        form.addRow("Rule Name *", self._name_input)

        self._type_combo = QComboBox(card)
        for code, label in _RULE_TYPES:
            self._type_combo.addItem(label, code)
        form.addRow("Rule Type *", self._type_combo)

        self._basis_combo = QComboBox(card)
        for code, label in _CALC_BASES:
            self._basis_combo.addItem(label, code)
        form.addRow("Calculation Basis *", self._basis_combo)

        self._effective_from_edit = QDateEdit(card)
        self._effective_from_edit.setCalendarPopup(True)
        self._effective_from_edit.setDate(QDate(2024, 1, 1))
        form.addRow("Effective From *", self._effective_from_edit)

        self._effective_to_cb = QCheckBox("Set expiry date", card)
        self._effective_to_cb.stateChanged.connect(self._on_to_toggle)
        form.addRow("", self._effective_to_cb)

        self._effective_to_edit = QDateEdit(card)
        self._effective_to_edit.setCalendarPopup(True)
        self._effective_to_edit.setDate(QDate(2024, 12, 31))
        self._effective_to_edit.setEnabled(False)
        form.addRow("Effective To", self._effective_to_edit)

        if is_edit:
            self._active_cb = QCheckBox("Active", card)
            self._active_cb.setChecked(True)
            form.addRow("Status", self._active_cb)

        layout.addWidget(card)

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

        if is_edit:
            self._load_existing()

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_rule_set_form", dialog=True)

    def _on_to_toggle(self) -> None:
        self._effective_to_edit.setEnabled(self._effective_to_cb.isChecked())

    def _set_combo_value(self, combo: QComboBox, value: str | None) -> None:
        if value is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _load_existing(self) -> None:
        if self._rule_set_id is None:
            return
        try:
            rs = self._sr.payroll_rule_service.get_rule_set(self._company_id, self._rule_set_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._code_input.setText(rs.rule_code)
        self._name_input.setText(rs.rule_name)
        self._set_combo_value(self._type_combo, rs.rule_type_code)
        self._set_combo_value(self._basis_combo, rs.calculation_basis_code)
        ef = rs.effective_from
        self._effective_from_edit.setDate(QDate(ef.year, ef.month, ef.day))
        if rs.effective_to:
            self._effective_to_cb.setChecked(True)
            et = rs.effective_to
            self._effective_to_edit.setDate(QDate(et.year, et.month, et.day))
        if hasattr(self, "_active_cb"):
            self._active_cb.setChecked(rs.is_active)

    def _submit(self) -> None:
        self._error_label.hide()
        from datetime import date as _date
        ef_qd = self._effective_from_edit.date()
        effective_from = _date(ef_qd.year(), ef_qd.month(), ef_qd.day())
        effective_to = None
        if self._effective_to_cb.isChecked():
            et_qd = self._effective_to_edit.date()
            effective_to = _date(et_qd.year(), et_qd.month(), et_qd.day())
        is_active = self._active_cb.isChecked() if hasattr(self, "_active_cb") else True

        try:
            if self._rule_set_id is None:
                self._sr.payroll_rule_service.create_rule_set(
                    self._company_id,
                    CreatePayrollRuleSetCommand(
                        rule_code=self._code_input.text().strip(),
                        rule_name=self._name_input.text().strip(),
                        rule_type_code=self._type_combo.currentData(),
                        effective_from=effective_from,
                        calculation_basis_code=self._basis_combo.currentData(),
                        effective_to=effective_to,
                    ),
                )
            else:
                self._sr.payroll_rule_service.update_rule_set(
                    self._company_id,
                    self._rule_set_id,
                    UpdatePayrollRuleSetCommand(
                        rule_code=self._code_input.text().strip(),
                        rule_name=self._name_input.text().strip(),
                        rule_type_code=self._type_combo.currentData(),
                        effective_from=effective_from,
                        calculation_basis_code=self._basis_combo.currentData(),
                        is_active=is_active,
                        effective_to=effective_to,
                    ),
                )
            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
