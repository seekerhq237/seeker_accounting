"""EmployeeHireWizardDialog — guided hire flow orchestrating employee,
compensation, and component-assignment services.

Steps:

1. **Identity**       — number, name, contact.
2. **Employment**     — hire date, department, position.
3. **Compensation**   — first profile: basic salary, currency, effective.
4. **Components**     — opt-in recurring assignments from active catalog.
5. **Review / Done**  — commit in order (employee → profile → assignments).

The existing ``EmployeeFormDialog`` remains available as the expert
fallback. This wizard is a recommended path, not a replacement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.employee_dto import CreateEmployeeCommand
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreateCompensationProfileCommand,
    CreateComponentAssignmentCommand,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row


_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmployeeHireWizardResult:
    employee_id: int
    profile_id: int | None
    assignment_ids: tuple[int, ...]
    summary: str


class EmployeeHireWizardDialog(BaseDialog):
    """6-step guided dialog — see module docstring."""

    _STEP_LABELS = (
        "1. Identity",
        "2. Employment",
        "3. Compensation",
        "4. Payment",
        "5. Components",
        "6. Review",
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._result: EmployeeHireWizardResult | None = None
        self._current_step = 0

        super().__init__(
            "Hire Employee",
            parent,
            help_key="wizard.employee_hire",
        )
        self.setObjectName("EmployeeHireWizardDialog")
        self.resize(720, 620)

        intro = QLabel(
            "Create an employee, first compensation profile, and "
            "recurring component assignments in a single guided flow.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)
        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self.body_layout.addWidget(self._build_step_header())

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_stack(), 1)
        self._build_buttons()
        self._load_defaults()
        self._update_step_pills()
        self._update_buttons()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def result_payload(self) -> EmployeeHireWizardResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> EmployeeHireWizardResult | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog.exec()
        return dialog.result_payload

    # ── Step header ───────────────────────────────────────────────────

    def _build_step_header(self) -> QWidget:
        header = QWidget(self)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._step_pills: list[QLabel] = []
        for text in self._STEP_LABELS:
            pill = QLabel(text, header)
            pill.setObjectName("WizardStepPill")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(pill)
            self._step_pills.append(pill)
        layout.addStretch(1)
        return header

    # ── Stack ─────────────────────────────────────────────────────────

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_identity_page())
        self._stack.addWidget(self._build_employment_page())
        self._stack.addWidget(self._build_compensation_page())
        self._stack.addWidget(self._build_payment_page())
        self._stack.addWidget(self._build_components_page())
        self._stack.addWidget(self._build_review_page())
        self._stack.addWidget(self._build_done_page())
        return self._stack

    def _build_identity_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Employee Identity")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._employee_number_edit = QLineEdit(card)
        self._employee_number_edit.setPlaceholderText("EMP001")
        grid.addWidget(create_field_block("Employee Number *", self._employee_number_edit), 0, 0)

        self._first_name_edit = QLineEdit(card)
        grid.addWidget(create_field_block("First Name *", self._first_name_edit), 0, 1)

        self._last_name_edit = QLineEdit(card)
        grid.addWidget(create_field_block("Last Name *", self._last_name_edit), 1, 0)

        self._display_name_edit = QLineEdit(card)
        self._display_name_edit.setPlaceholderText("First Last")
        grid.addWidget(create_field_block("Display Name", self._display_name_edit), 1, 1)

        self._email_edit = QLineEdit(card)
        grid.addWidget(create_field_block("Email", self._email_edit), 2, 0)

        self._phone_edit = QLineEdit(card)
        grid.addWidget(create_field_block("Phone", self._phone_edit), 2, 1)

        card.layout().addLayout(grid)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_employment_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Employment Details")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._hire_date_edit = QDateEdit(card)
        self._hire_date_edit.setCalendarPopup(True)
        self._hire_date_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(create_field_block("Hire Date *", self._hire_date_edit), 0, 0)

        self._department_combo = QComboBox(card)
        grid.addWidget(create_field_block("Department", self._department_combo), 0, 1)

        self._position_combo = QComboBox(card)
        grid.addWidget(create_field_block("Position", self._position_combo), 1, 0)

        self._currency_edit = QLineEdit(card)
        self._currency_edit.setPlaceholderText("XAF")
        grid.addWidget(create_field_block("Base Currency *", self._currency_edit), 1, 1)

        self._tax_id_edit = QLineEdit(card)
        grid.addWidget(create_field_block("Tax Identifier", self._tax_id_edit), 2, 0)

        self._cnps_edit = QLineEdit(card)
        grid.addWidget(create_field_block("CNPS Number", self._cnps_edit), 2, 1)

        card.layout().addLayout(grid)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_compensation_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("First Compensation Profile")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._profile_name_edit = QLineEdit(card)
        self._profile_name_edit.setPlaceholderText("Standard")
        grid.addWidget(create_field_block("Profile Name *", self._profile_name_edit), 0, 0)

        self._salary_spin = QDoubleSpinBox(card)
        self._salary_spin.setMaximum(1_000_000_000.0)
        self._salary_spin.setDecimals(2)
        self._salary_spin.setGroupSeparatorShown(True)
        grid.addWidget(create_field_block("Basic Salary *", self._salary_spin), 0, 1)

        self._profile_currency_edit = QLineEdit(card)
        self._profile_currency_edit.setPlaceholderText("XAF")
        grid.addWidget(create_field_block("Currency *", self._profile_currency_edit), 1, 0)

        self._effective_from_edit = QDateEdit(card)
        self._effective_from_edit.setCalendarPopup(True)
        self._effective_from_edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(create_field_block("Effective From *", self._effective_from_edit), 1, 1)

        card.layout().addLayout(grid)
        outer.addWidget(card)

        hint = QLabel(
            "You can add further profiles later (e.g. for raises or "
            "allowance restructuring).",
            page,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        outer.addStretch(1)
        return page

    def _build_payment_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = self._card("Payment Account")
        hint = QLabel(
            "Select the default account used to settle this employee's net pay "
            "(bank or cash). Optional \u2014 skip to assign later.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._payment_account_combo = QComboBox(card)
        card.layout().addWidget(
            create_field_block("Default Payment Account", self._payment_account_combo)
        )

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_components_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = self._card("Recurring Component Assignments")
        hint = QLabel(
            "Select statutory and recurring components that apply to this employee. "
            "Deductions such as CNPS, IRPP, TDL are typical selections.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._components_list = QListWidget(card)
        self._components_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        card.layout().addWidget(self._components_list, 1)

        outer.addWidget(card, 1)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Review")
        self._review_label = QLabel(card)
        self._review_label.setObjectName("DialogSectionSummary")
        self._review_label.setWordWrap(True)
        card.layout().addWidget(self._review_label)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Employee hired")
        self._done_label = QLabel(card)
        self._done_label.setObjectName("DialogSectionSummary")
        self._done_label.setWordWrap(True)
        card.layout().addWidget(self._done_label)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _card(self, title: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        tlabel = QLabel(title, card)
        tlabel.setObjectName("DialogSectionTitle")
        layout.addWidget(tlabel)
        return card

    # ── Buttons ───────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        self._back_button = QPushButton("Back", self)
        self._back_button.setProperty("variant", "secondary")
        self._back_button.clicked.connect(self._go_back)
        self.button_box.addButton(self._back_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._next_button = QPushButton("Next", self)
        self._next_button.setProperty("variant", "primary")
        self._next_button.clicked.connect(self._go_next)
        self.button_box.addButton(self._next_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._apply_button = QPushButton("Create Employee", self)
        self._apply_button.setProperty("variant", "primary")
        self._apply_button.clicked.connect(self._handle_apply)
        self.button_box.addButton(self._apply_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._close_button = QPushButton("Cancel", self)
        self._close_button.setProperty("variant", "ghost")
        self._close_button.clicked.connect(self.reject)
        self.button_box.addButton(self._close_button, QDialogButtonBox.ButtonRole.RejectRole)

    # ── Defaults / navigation ─────────────────────────────────────────

    def _load_defaults(self) -> None:
        today = date.today()
        self._hire_date_edit.setDate(QDate(today.year, today.month, today.day))
        self._effective_from_edit.setDate(QDate(today.year, today.month, 1))

        # Departments / positions
        try:
            deps = self._registry.payroll_setup_service.list_departments(self._company_id)
        except Exception:  # noqa: BLE001
            deps = []
        self._department_combo.addItem("— None —", None)
        for d in deps:
            self._department_combo.addItem(f"{d.code} — {d.name}", d.id)

        try:
            poss = self._registry.payroll_setup_service.list_positions(self._company_id)
        except Exception:  # noqa: BLE001
            poss = []
        self._position_combo.addItem("— None —", None)
        for p in poss:
            self._position_combo.addItem(f"{p.code} — {p.name}", p.id)

        # Currency default
        try:
            settings = self._registry.payroll_setup_service.get_company_payroll_settings(
                self._company_id
            )
        except Exception:  # noqa: BLE001
            settings = None
        default_currency = (
            settings.default_payroll_currency_code if settings else "XAF"
        ) or "XAF"
        self._currency_edit.setText(default_currency)
        self._profile_currency_edit.setText(default_currency)

        # Payment accounts (cash / bank)
        try:
            accounts = self._registry.chart_of_accounts_service.list_accounts(
                self._company_id, active_only=True
            )
        except Exception:  # noqa: BLE001
            accounts = []
        self._payment_account_combo.clear()
        self._payment_account_combo.addItem("— None (assign later) —", None)
        for acc in accounts:
            type_code = (acc.account_type_code or "").lower()
            if type_code not in ("cash", "bank", "cash_bank"):
                continue
            if not acc.allow_manual_posting or acc.is_control_account:
                continue
            self._payment_account_combo.addItem(
                f"{acc.account_code} — {acc.account_name}", acc.id
            )

        # Components list (active only)
        try:
            components = self._registry.payroll_component_service.list_components(
                self._company_id
            )
        except Exception:  # noqa: BLE001
            components = []
        self._components_list.clear()
        for comp in components:
            if not getattr(comp, "is_active", True):
                continue
            item = QListWidgetItem(self._components_list)
            checkbox = QCheckBox(
                f"{comp.component_code} — {comp.component_name} "
                f"[{comp.component_type_code}]"
            )
            # Pre-select deductions and taxes (typical recurring items).
            if (comp.component_type_code or "").lower() in ("deduction", "tax"):
                checkbox.setChecked(True)
            item.setSizeHint(checkbox.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, comp.id)
            self._components_list.addItem(item)
            self._components_list.setItemWidget(item, checkbox)

    def _go_next(self) -> None:
        if self._current_step == 0 and not self._validate_identity():
            return
        if self._current_step == 1 and not self._validate_employment():
            return
        if self._current_step == 2 and not self._validate_compensation():
            return
        if self._current_step == 5:
            self._handle_apply()
            return
        self._current_step += 1
        if self._current_step == 5:
            self._refresh_review()
        self._stack.setCurrentIndex(self._current_step)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _go_back(self) -> None:
        if self._current_step <= 0:
            return
        self._current_step -= 1
        self._stack.setCurrentIndex(self._current_step)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _update_step_pills(self) -> None:
        for index, pill in enumerate(self._step_pills):
            if index < self._current_step:
                pill.setProperty("completed", "true")
                pill.setProperty("current", "false")
            elif index == self._current_step:
                pill.setProperty("completed", "false")
                pill.setProperty("current", "true")
            else:
                pill.setProperty("completed", "false")
                pill.setProperty("current", "false")
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _update_buttons(self) -> None:
        on_review = self._current_step == 5
        on_done = self._current_step == 6
        self._back_button.setVisible(0 < self._current_step and not on_done)
        self._next_button.setVisible(not on_review and not on_done)
        self._apply_button.setVisible(on_review)
        self._close_button.setText("Close" if on_done else "Cancel")

    # ── Validation ────────────────────────────────────────────────────

    def _validate_identity(self) -> bool:
        if not self._employee_number_edit.text().strip():
            self._set_error("Employee number is required.")
            return False
        if not self._first_name_edit.text().strip():
            self._set_error("First name is required.")
            return False
        if not self._last_name_edit.text().strip():
            self._set_error("Last name is required.")
            return False
        return True

    def _validate_employment(self) -> bool:
        if not self._currency_edit.text().strip():
            self._set_error("Base currency is required.")
            return False
        return True

    def _validate_compensation(self) -> bool:
        if not self._profile_name_edit.text().strip():
            self._set_error("Profile name is required.")
            return False
        if self._salary_spin.value() <= 0:
            self._set_error("Basic salary must be greater than zero.")
            return False
        if not self._profile_currency_edit.text().strip():
            self._set_error("Profile currency is required.")
            return False
        return True

    # ── Selected components ───────────────────────────────────────────

    def _selected_component_ids(self) -> list[int]:
        ids: list[int] = []
        for i in range(self._components_list.count()):
            item = self._components_list.item(i)
            widget = self._components_list.itemWidget(item)
            if isinstance(widget, QCheckBox) and widget.isChecked():
                ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    # ── Review ────────────────────────────────────────────────────────

    def _refresh_review(self) -> None:
        selected = self._selected_component_ids()
        display_name = (
            self._display_name_edit.text().strip()
            or f"{self._first_name_edit.text().strip()} {self._last_name_edit.text().strip()}"
        )
        lines = [
            f"<b>Employee</b>: {self._employee_number_edit.text().strip()} — {display_name}",
            f"<b>Hire date</b>: {self._hire_date_edit.date().toPython().isoformat()}",
            (
                f"<b>Department / Position</b>: "
                f"{self._department_combo.currentText()} / {self._position_combo.currentText()}"
            ),
            (
                f"<b>Tax / CNPS</b>: "
                f"{self._tax_id_edit.text().strip() or '—'} / "
                f"{self._cnps_edit.text().strip() or '—'}"
            ),
            (
                f"<b>Compensation</b>: {self._salary_spin.value():,.2f} "
                f"{self._profile_currency_edit.text().strip()} "
                f"(effective {self._effective_from_edit.date().toPython().isoformat()})"
            ),
            f"<b>Payment account</b>: {self._payment_account_combo.currentText()}",
            f"<b>Component assignments</b>: {len(selected)} selected",
        ]
        self._review_label.setText("<br>".join(lines))

    # ── Commit ────────────────────────────────────────────────────────

    def _handle_apply(self) -> None:
        self._set_error(None)
        self._apply_button.setEnabled(False)
        try:
            employee = self._commit_employee()
            if employee is None:
                return
            profile = self._commit_profile(employee.id)
            assignment_ids = self._commit_assignments(employee.id)
        finally:
            self._apply_button.setEnabled(True)

        display_name = employee.display_name
        summary_bits = [f"Employee {employee.employee_number} — {display_name} created."]
        if profile is not None:
            summary_bits.append(
                f"Compensation profile '{profile.profile_name}' "
                f"({profile.basic_salary:,.2f} {profile.currency_code}) effective "
                f"{profile.effective_from.isoformat()}."
            )
        summary_bits.append(f"{len(assignment_ids)} component assignment(s) created.")
        if self._payment_account_combo.currentData():
            summary_bits.append(
                f"Payment account: {self._payment_account_combo.currentText()}."
            )
        summary_bits.append(
            "First-period proration preview coming in a future update \u2014 "
            "run the next payroll to see the prorated amounts."
        )
        summary = " ".join(summary_bits)

        self._result = EmployeeHireWizardResult(
            employee_id=employee.id,
            profile_id=profile.id if profile is not None else None,
            assignment_ids=tuple(assignment_ids),
            summary=summary,
        )
        self._done_label.setText(summary)
        self._current_step = 6
        self._stack.setCurrentIndex(self._current_step)
        self._update_step_pills()
        self._update_buttons()

    def _commit_employee(self):
        display_name = (
            self._display_name_edit.text().strip()
            or f"{self._first_name_edit.text().strip()} {self._last_name_edit.text().strip()}"
        )
        cmd = CreateEmployeeCommand(
            employee_number=self._employee_number_edit.text().strip(),
            display_name=display_name,
            first_name=self._first_name_edit.text().strip(),
            last_name=self._last_name_edit.text().strip(),
            hire_date=self._hire_date_edit.date().toPython(),
            base_currency_code=self._currency_edit.text().strip(),
            department_id=self._department_combo.currentData(),
            position_id=self._position_combo.currentData(),
            email=self._email_edit.text().strip() or None,
            phone=self._phone_edit.text().strip() or None,
            tax_identifier=self._tax_id_edit.text().strip() or None,
            cnps_number=self._cnps_edit.text().strip() or None,
            default_payment_account_id=self._payment_account_combo.currentData(),
        )
        try:
            return self._registry.employee_service.create_employee(self._company_id, cmd)
        except (ValidationError, ConflictError, PermissionDeniedError, NotFoundError) as exc:
            self._set_error(str(exc))
            return None

    def _commit_profile(self, employee_id: int):
        try:
            salary = Decimal(str(self._salary_spin.value())).quantize(Decimal("0.01"))
        except InvalidOperation:
            self._set_error("Invalid salary amount.")
            return None
        cmd = CreateCompensationProfileCommand(
            employee_id=employee_id,
            profile_name=self._profile_name_edit.text().strip(),
            basic_salary=salary,
            currency_code=self._profile_currency_edit.text().strip(),
            effective_from=self._effective_from_edit.date().toPython(),
        )
        try:
            return self._registry.compensation_profile_service.create_profile(
                self._company_id, cmd
            )
        except (ValidationError, ConflictError, PermissionDeniedError, NotFoundError) as exc:
            self._set_error(f"Compensation profile: {exc}")
            return None

    def _commit_assignments(self, employee_id: int) -> list[int]:
        created: list[int] = []
        effective = self._effective_from_edit.date().toPython()
        for component_id in self._selected_component_ids():
            cmd = CreateComponentAssignmentCommand(
                employee_id=employee_id,
                component_id=component_id,
                effective_from=effective,
            )
            try:
                dto = self._registry.component_assignment_service.create_assignment(
                    self._company_id, cmd
                )
                created.append(dto.id)
            except (ValidationError, ConflictError, PermissionDeniedError, NotFoundError) as exc:
                _log.warning(
                    "EmployeeHireWizard: assignment for component %s failed: %s",
                    component_id,
                    exc,
                )
        return created

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()
