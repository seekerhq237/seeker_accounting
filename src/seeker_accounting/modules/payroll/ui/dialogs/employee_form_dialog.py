from __future__ import annotations

import logging

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
from PySide6.QtCore import QDate

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.employee_dto import (
    CreateEmployeeCommand,
    UpdateEmployeeCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error

_log = logging.getLogger(__name__)


class EmployeeFormDialog(QDialog):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        employee_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._company_id = company_id
        self._employee_id = employee_id

        is_edit = employee_id is not None
        self.setWindowTitle(f"{'Edit' if is_edit else 'New'} Employee — {company_name}")
        self.setModal(True)
        self.resize(500, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Identity card ─────────────────────────────────────────────────────
        id_card = QFrame(self)
        id_card.setObjectName("PageCard")
        id_form = QFormLayout(id_card)
        id_form.setContentsMargins(18, 16, 18, 16)
        id_form.setSpacing(10)
        id_hdr = QLabel("Employee Identity", id_card)
        id_hdr.setObjectName("CardTitle")
        id_form.addRow(id_hdr)

        self._number_input = QLineEdit(id_card)
        self._number_input.setPlaceholderText("Employee number (e.g. EMP001)")
        id_form.addRow("Employee Number *", self._number_input)

        self._display_name_input = QLineEdit(id_card)
        self._display_name_input.setPlaceholderText("Display name")
        id_form.addRow("Display Name *", self._display_name_input)

        self._first_name_input = QLineEdit(id_card)
        id_form.addRow("First Name *", self._first_name_input)

        self._last_name_input = QLineEdit(id_card)
        id_form.addRow("Last Name *", self._last_name_input)

        layout.addWidget(id_card)

        # ── Employment card ───────────────────────────────────────────────────
        emp_card = QFrame(self)
        emp_card.setObjectName("PageCard")
        emp_form = QFormLayout(emp_card)
        emp_form.setContentsMargins(18, 16, 18, 16)
        emp_form.setSpacing(10)
        emp_hdr = QLabel("Employment Details", emp_card)
        emp_hdr.setObjectName("CardTitle")
        emp_form.addRow(emp_hdr)

        self._hire_date_edit = QDateEdit(emp_card)
        self._hire_date_edit.setCalendarPopup(True)
        self._hire_date_edit.setDate(QDate.currentDate())
        emp_form.addRow("Hire Date *", self._hire_date_edit)

        self._termination_date_cb = QCheckBox("Set termination date", emp_card)
        self._termination_date_cb.stateChanged.connect(self._on_termination_toggle)
        emp_form.addRow("", self._termination_date_cb)

        self._termination_date_edit = QDateEdit(emp_card)
        self._termination_date_edit.setCalendarPopup(True)
        self._termination_date_edit.setDate(QDate.currentDate())
        self._termination_date_edit.setEnabled(False)
        emp_form.addRow("Termination Date", self._termination_date_edit)

        self._dept_combo = QComboBox(emp_card)
        emp_form.addRow("Department", self._dept_combo)

        self._pos_combo = QComboBox(emp_card)
        emp_form.addRow("Position", self._pos_combo)

        self._currency_combo = QComboBox(emp_card)
        emp_form.addRow("Base Currency *", self._currency_combo)

        if is_edit:
            self._active_cb = QCheckBox("Active", emp_card)
            self._active_cb.setChecked(True)
            emp_form.addRow("Status", self._active_cb)

        layout.addWidget(emp_card)

        # ── Contact card ──────────────────────────────────────────────────────
        contact_card = QFrame(self)
        contact_card.setObjectName("PageCard")
        contact_form = QFormLayout(contact_card)
        contact_form.setContentsMargins(18, 16, 18, 16)
        contact_form.setSpacing(10)
        contact_hdr = QLabel("Contact & Tax", contact_card)
        contact_hdr.setObjectName("CardTitle")
        contact_form.addRow(contact_hdr)

        self._phone_input = QLineEdit(contact_card)
        self._phone_input.setPlaceholderText("Optional")
        contact_form.addRow("Phone", self._phone_input)

        self._email_input = QLineEdit(contact_card)
        self._email_input.setPlaceholderText("Optional")
        contact_form.addRow("Email", self._email_input)

        self._tax_id_input = QLineEdit(contact_card)
        self._tax_id_input.setPlaceholderText("NIU / NIF (optional)")
        contact_form.addRow("Tax Identifier", self._tax_id_input)

        self._cnps_input = QLineEdit(contact_card)
        self._cnps_input.setPlaceholderText("CNPS immatriculation (optional)")
        contact_form.addRow("CNPS Number", self._cnps_input)

        self._payment_account_combo = QComboBox(contact_card)
        self._payment_account_combo.setSizePolicy(
            self._payment_account_combo.sizePolicy().horizontalPolicy(),
            self._payment_account_combo.sizePolicy().verticalPolicy(),
        )
        contact_form.addRow("Payment Account", self._payment_account_combo)

        layout.addWidget(contact_card)

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

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.employee_form", dialog=True)

        self._load_lookups()
        if is_edit:
            self._load_existing()
        else:
            self._suggest_code()

    # ── Load helpers ──────────────────────────────────────────────────────────

    def _suggest_code(self) -> None:
        try:
            code = self._sr.code_suggestion_service.suggest("employee", self._company_id)
            self._number_input.setText(code)
        except Exception:
            pass

    def _load_lookups(self) -> None:
        # Currencies
        try:
            currencies = self._sr.reference_data_service.list_active_currencies()
        except Exception:
            currencies = []
        self._currency_combo.clear()
        self._currency_combo.addItem("— Select currency —", None)
        for c in currencies:
            self._currency_combo.addItem(f"{c.code} — {c.name}", c.code)
        if not currencies:
            self._currency_combo.addItem("(No active currencies available)", None)

        # Departments
        try:
            depts = self._sr.payroll_setup_service.list_departments(self._company_id)
        except Exception:
            depts = []
        self._dept_combo.clear()
        self._dept_combo.addItem("— None —", None)
        for d in depts:
            self._dept_combo.addItem(f"{d.code} — {d.name}", d.id)

        # Positions
        try:
            positions = self._sr.payroll_setup_service.list_positions(self._company_id)
        except Exception:
            positions = []
        self._pos_combo.clear()
        self._pos_combo.addItem("— None —", None)
        for p in positions:
            self._pos_combo.addItem(f"{p.code} — {p.name}", p.id)

        # Payment accounts
        try:
            accounts = self._sr.financial_account_service.list_financial_accounts(
                self._company_id, active_only=True
            )
        except Exception:
            accounts = []
        self._payment_account_combo.clear()
        self._payment_account_combo.addItem("— None (unspecified) —", None)
        for acct in accounts:
            label = acct.name
            if hasattr(acct, "bank_name") and acct.bank_name:
                label = f"{acct.name} ({acct.bank_name})"
            self._payment_account_combo.addItem(label, acct.id)

    def _load_existing(self) -> None:
        if self._employee_id is None:
            return
        try:
            emp = self._sr.employee_service.get_employee(self._company_id, self._employee_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return
        self._number_input.setText(emp.employee_number)
        self._display_name_input.setText(emp.display_name)
        self._first_name_input.setText(emp.first_name)
        self._last_name_input.setText(emp.last_name)
        self._hire_date_edit.setDate(QDate(emp.hire_date.year, emp.hire_date.month, emp.hire_date.day))
        if emp.termination_date:
            self._termination_date_cb.setChecked(True)
            self._termination_date_edit.setDate(
                QDate(emp.termination_date.year, emp.termination_date.month, emp.termination_date.day)
            )
        self._set_combo_value(self._currency_combo, emp.base_currency_code)
        self._set_combo_value_int(self._dept_combo, emp.department_id)
        self._set_combo_value_int(self._pos_combo, emp.position_id)
        self._phone_input.setText(emp.phone or "")
        self._email_input.setText(emp.email or "")
        self._tax_id_input.setText(emp.tax_identifier or "")
        self._cnps_input.setText(emp.cnps_number or "")
        self._set_combo_value_int(self._payment_account_combo, emp.default_payment_account_id)
        if hasattr(self, "_active_cb"):
            self._active_cb.setChecked(emp.is_active)

    def _on_termination_toggle(self) -> None:
        self._termination_date_edit.setEnabled(self._termination_date_cb.isChecked())

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

    # ── Submit ────────────────────────────────────────────────────────────────

    def _submit(self) -> None:
        self._error_label.hide()
        from datetime import date as _date
        hire_qd = self._hire_date_edit.date()
        hire_date = _date(hire_qd.year(), hire_qd.month(), hire_qd.day())
        termination_date = None
        if self._termination_date_cb.isChecked():
            td = self._termination_date_edit.date()
            termination_date = _date(td.year(), td.month(), td.day())

        currency = self._currency_combo.currentData()
        if not currency:
            self._show_error("Base currency is required.")
            return

        try:
            if self._employee_id is None:
                cmd = CreateEmployeeCommand(
                    employee_number=self._number_input.text().strip(),
                    display_name=self._display_name_input.text().strip(),
                    first_name=self._first_name_input.text().strip(),
                    last_name=self._last_name_input.text().strip(),
                    hire_date=hire_date,
                    base_currency_code=currency,
                    department_id=self._dept_combo.currentData(),
                    position_id=self._pos_combo.currentData(),
                    termination_date=termination_date,
                    phone=self._phone_input.text().strip() or None,
                    email=self._email_input.text().strip() or None,
                    tax_identifier=self._tax_id_input.text().strip() or None,
                    cnps_number=self._cnps_input.text().strip() or None,
                    default_payment_account_id=self._payment_account_combo.currentData(),
                )
                self._sr.employee_service.create_employee(self._company_id, cmd)
            else:
                is_active = self._active_cb.isChecked() if hasattr(self, "_active_cb") else True
                cmd_u = UpdateEmployeeCommand(
                    employee_number=self._number_input.text().strip(),
                    display_name=self._display_name_input.text().strip(),
                    first_name=self._first_name_input.text().strip(),
                    last_name=self._last_name_input.text().strip(),
                    hire_date=hire_date,
                    base_currency_code=currency,
                    is_active=is_active,
                    department_id=self._dept_combo.currentData(),
                    position_id=self._pos_combo.currentData(),
                    termination_date=termination_date,
                    phone=self._phone_input.text().strip() or None,
                    email=self._email_input.text().strip() or None,
                    tax_identifier=self._tax_id_input.text().strip() or None,
                    cnps_number=self._cnps_input.text().strip() or None,
                    default_payment_account_id=self._payment_account_combo.currentData(),
                )
                self._sr.employee_service.update_employee(
                    self._company_id, self._employee_id, cmd_u
                )
            self.accept()
        except (ValidationError, ConflictError) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()
