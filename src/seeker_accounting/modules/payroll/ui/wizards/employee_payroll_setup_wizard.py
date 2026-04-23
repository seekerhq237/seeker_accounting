"""EmployeePayrollSetupWizardDialog — adaptive payroll-readiness wizard.

Unlike the :class:`EmployeeHireWizardDialog` which creates a brand-new
employee, this wizard takes an **existing** employee and brings them to
fully payroll-ready state by filling in only the gaps it detects:

* Tax identifier + CNPS number       (if either is missing)
* Default payment account            (if not set)
* Active compensation profile        (if none covers today)
* Active recurring component assignments (if none exist)

The intro step shows a readiness dashboard; the user can skip any
detected-but-optional step with ``Skip``. Mandatory gaps cannot be
skipped. On commit, the wizard:

1. issues one ``update_employee`` call with the combined tax + payment
   edits (only if anything changed);
2. creates a compensation profile via
   ``compensation_profile_service.create_profile`` if requested;
3. creates component assignments via
   ``component_assignment_service.create_assignment`` if requested.

Result payload summarizes what was done and which gaps remain.
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
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreateCompensationProfileCommand,
    CreateComponentAssignmentCommand,
)
from seeker_accounting.modules.payroll.dto.employee_dto import (
    UpdateEmployeeCommand,
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


# ── Steps ─────────────────────────────────────────────────────────────────────
# Steps are selected adaptively. The intro and review pages always run;
# gap pages only run if the readiness scan detects an issue.

STEP_INTRO = "intro"
STEP_TAX_CNPS = "tax_cnps"
STEP_PAYMENT = "payment"
STEP_COMP = "comp"
STEP_COMPONENTS = "components"
STEP_REVIEW = "review"
STEP_DONE = "done"


_STEP_LABELS = {
    STEP_INTRO:      "Readiness",
    STEP_TAX_CNPS:   "Tax & CNPS",
    STEP_PAYMENT:    "Payment",
    STEP_COMP:       "Compensation",
    STEP_COMPONENTS: "Components",
    STEP_REVIEW:     "Review",
    STEP_DONE:       "Done",
}


@dataclass(frozen=True, slots=True)
class EmployeePayrollSetupResult:
    employee_id: int
    updated_employee: bool
    tax_identifier_set: bool
    cnps_number_set: bool
    payment_account_set: bool
    compensation_profile_id: int | None
    assignment_ids: tuple[int, ...] = field(default_factory=tuple)
    skipped_gaps: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


class EmployeePayrollSetupWizardDialog(BaseDialog):
    """Adaptive wizard that brings an existing employee to payroll-ready state."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        employee_id: int,
        parent: QWidget | None = None,
    ) -> None:
        self._registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._employee_id = employee_id

        self._employee = None
        self._components: list = []
        self._financial_accounts: list = []
        self._gaps: dict[str, bool] = {}
        self._active_steps: list[str] = []
        self._current_index = 0
        self._skipped: set[str] = set()
        self._result: EmployeePayrollSetupResult | None = None
        self._committed = False

        super().__init__(
            "Employee Payroll Setup",
            parent,
            help_key="wizard.employee_payroll_setup",
        )
        self.setObjectName("EmployeePayrollSetupWizardDialog")
        self.resize(940, 680)

        # Load employee + context
        self._load_context()
        if self._employee is None:
            # Parent will see result_payload is None; we still need
            # a minimal widget so BaseDialog lifecycle is clean.
            err = QLabel("Employee could not be loaded.", self)
            err.setObjectName("DialogErrorLabel")
            self.body_layout.addWidget(err)
            self._build_buttons()
            self._apply_button.hide()
            self._next_button.hide()
            self._back_button.hide()
            return

        intro = QLabel(
            "This wizard inspects the selected employee's payroll profile "
            "and walks you through only the pieces that still need to be "
            "set up. Optional gaps can be skipped.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)
        self.body_layout.addWidget(
            create_label_value_row(
                "Employee",
                f"{self._employee.display_name}  ·  {self._employee.employee_number}",
                self,
            )
        )
        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self._scan_gaps()
        self._compute_active_steps()
        self.body_layout.addWidget(self._build_step_header())

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_stack(), 1)
        self._build_buttons()
        self._prefill_from_employee()
        self._update_step_pills()
        self._update_buttons()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def result_payload(self) -> EmployeePayrollSetupResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        employee_id: int,
        parent: QWidget | None = None,
    ) -> EmployeePayrollSetupResult | None:
        dialog = cls(
            service_registry, company_id, company_name, employee_id, parent=parent,
        )
        dialog.exec()
        return dialog.result_payload

    # ── Context loading ───────────────────────────────────────────────

    def _load_context(self) -> None:
        try:
            self._employee = self._registry.employee_service.get_employee(
                self._company_id, self._employee_id,
            )
        except (NotFoundError, PermissionDeniedError):
            self._employee = None
            return
        try:
            self._components = self._registry.payroll_component_service.list_components(
                self._company_id, active_only=True,
            )
        except Exception:  # noqa: BLE001
            self._components = []
        try:
            self._financial_accounts = (
                self._registry.financial_account_service.list_financial_accounts(
                    self._company_id, active_only=True,
                )
            )
        except Exception:  # noqa: BLE001
            self._financial_accounts = []

    def _scan_gaps(self) -> None:
        emp = self._employee
        today = date.today()

        tax_missing = not (emp.tax_identifier and emp.cnps_number)
        payment_missing = emp.default_payment_account_id is None

        try:
            profiles = self._registry.compensation_profile_service.list_profiles(
                self._company_id, employee_id=self._employee_id, active_only=True,
            )
        except Exception:  # noqa: BLE001
            profiles = []
        has_comp = any(
            (p.effective_from is None or p.effective_from <= today)
            and (p.effective_to is None or p.effective_to >= today)
            for p in profiles
        )

        try:
            assignments = (
                self._registry.component_assignment_service.list_assignments(
                    self._company_id, employee_id=self._employee_id, active_only=True,
                )
            )
        except Exception:  # noqa: BLE001
            assignments = []
        has_assignments = bool(assignments)

        self._gaps = {
            STEP_TAX_CNPS: tax_missing,
            STEP_PAYMENT: payment_missing,
            STEP_COMP: not has_comp,
            STEP_COMPONENTS: not has_assignments,
        }
        self._current_profile_count = len(profiles)
        self._current_assignment_count = len(assignments)

    def _compute_active_steps(self) -> None:
        steps = [STEP_INTRO]
        for key in (STEP_TAX_CNPS, STEP_PAYMENT, STEP_COMP, STEP_COMPONENTS):
            if self._gaps.get(key):
                steps.append(key)
        steps.append(STEP_REVIEW)
        steps.append(STEP_DONE)
        self._active_steps = steps

    # ── Header ────────────────────────────────────────────────────────

    def _build_step_header(self) -> QWidget:
        header = QWidget(self)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._step_pills: list[QLabel] = []
        for key in self._active_steps:
            if key == STEP_DONE:
                continue
            pill = QLabel(_STEP_LABELS[key], header)
            pill.setObjectName("WizardStepPill")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(pill)
            self._step_pills.append(pill)
        layout.addStretch(1)
        return header

    # ── Pages ─────────────────────────────────────────────────────────

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._page_index: dict[str, int] = {}
        for key in self._active_steps:
            page = {
                STEP_INTRO: self._build_intro_page,
                STEP_TAX_CNPS: self._build_tax_page,
                STEP_PAYMENT: self._build_payment_page,
                STEP_COMP: self._build_comp_page,
                STEP_COMPONENTS: self._build_components_page,
                STEP_REVIEW: self._build_review_page,
                STEP_DONE: self._build_done_page,
            }[key]()
            self._page_index[key] = self._stack.addWidget(page)
        return self._stack

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

    # --- Intro ---
    def _build_intro_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Payroll Readiness")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        items = [
            ("Tax identifier & CNPS number", not self._gaps[STEP_TAX_CNPS]),
            ("Default payment account", not self._gaps[STEP_PAYMENT]),
            ("Active compensation profile", not self._gaps[STEP_COMP]),
            ("Recurring component assignments", not self._gaps[STEP_COMPONENTS]),
        ]
        for row, (label, ok) in enumerate(items):
            status = QLabel("✓ OK" if ok else "⚠ Missing", card)
            status.setStyleSheet(
                "color:#1a7a2e;" if ok else "color:#b25503;"
            )
            grid.addWidget(QLabel(label, card), row, 0)
            grid.addWidget(status, row, 1)
        card.layout().addLayout(grid)

        gap_count = sum(1 for v in self._gaps.values() if v)
        summary = QLabel(
            f"<b>{gap_count} gap(s) detected.</b> The wizard will walk you "
            f"through each one; you can skip optional gaps."
            if gap_count
            else "<b>This employee is payroll-ready.</b> The wizard will "
            "only ask you to confirm.",
            card,
        )
        summary.setObjectName("DialogSectionSummary")
        summary.setWordWrap(True)
        card.layout().addWidget(summary)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    # --- Tax & CNPS ---
    def _build_tax_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Tax Identifier & CNPS")

        hint = QLabel(
            "Statutory identifiers used during run calculation and "
            "remittance reporting. Both are recommended; you can skip if "
            "they will be captured later.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self._tax_edit = QLineEdit(card)
        self._tax_edit.setPlaceholderText("e.g. P123456789")
        grid.addWidget(create_field_block("Tax Identifier", self._tax_edit), 0, 0)

        self._cnps_edit = QLineEdit(card)
        self._cnps_edit.setPlaceholderText("e.g. 12-345678-9")
        grid.addWidget(create_field_block("CNPS Number", self._cnps_edit), 0, 1)
        card.layout().addLayout(grid)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    # --- Payment Account ---
    def _build_payment_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Default Payment Account")

        hint = QLabel(
            "Cash or bank account used by default when recording net-pay "
            "settlements for this employee.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._payment_combo = QComboBox(card)
        self._payment_combo.addItem("— None (decide per payment) —", None)
        for acct in self._financial_accounts:
            label = acct.name
            if hasattr(acct, "bank_name") and acct.bank_name:
                label = f"{acct.name} ({acct.bank_name})"
            self._payment_combo.addItem(label, acct.id)
        card.layout().addWidget(
            create_field_block("Payment Account", self._payment_combo)
        )

        if not self._financial_accounts:
            warn = QLabel(
                "<i>No active financial accounts are configured. You can "
                "skip this step; assign an account later once banks are "
                "set up.</i>",
                card,
            )
            warn.setWordWrap(True)
            card.layout().addWidget(warn)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    # --- Compensation profile ---
    def _build_comp_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Compensation Profile")

        hint = QLabel(
            "An active compensation profile is required for payroll "
            "calculation. Enter the basic salary effective from the date "
            "below. This step is mandatory.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self._profile_name_edit = QLineEdit(card)
        self._profile_name_edit.setText(
            f"{self._employee.display_name} — Base"
            if self._employee else ""
        )
        grid.addWidget(
            create_field_block("Profile Name *", self._profile_name_edit),
            0, 0, 1, 2,
        )

        self._basic_salary_edit = QDoubleSpinBox(card)
        self._basic_salary_edit.setDecimals(2)
        self._basic_salary_edit.setMaximum(1e12)
        self._basic_salary_edit.setGroupSeparatorShown(True)
        grid.addWidget(
            create_field_block("Basic Salary *", self._basic_salary_edit),
            1, 0,
        )

        self._currency_edit = QLineEdit(card)
        self._currency_edit.setText(self._employee.base_currency_code if self._employee else "")
        self._currency_edit.setMaxLength(3)
        grid.addWidget(
            create_field_block("Currency *", self._currency_edit),
            1, 1,
        )

        self._effective_from_edit = QDateEdit(card)
        self._effective_from_edit.setCalendarPopup(True)
        self._effective_from_edit.setDisplayFormat("yyyy-MM-dd")
        today = date.today()
        self._effective_from_edit.setDate(QDate(today.year, today.month, 1))
        grid.addWidget(
            create_field_block("Effective From *", self._effective_from_edit),
            2, 0,
        )

        card.layout().addLayout(grid)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    # --- Component assignments ---
    def _build_components_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Recurring Component Assignments")

        hint = QLabel(
            "Select the recurring components (deductions, employer "
            "contributions, taxes) that apply to this employee. You can "
            "add more assignments later from the employee hub.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._component_list = QListWidget(card)
        self._component_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        for comp in self._components:
            item = QListWidgetItem(
                f"{comp.component_code} — {comp.component_name}  [{comp.component_type_code}]"
            )
            item.setData(Qt.ItemDataRole.UserRole, comp.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # Pre-check deductions and taxes by default.
            pre_check = comp.component_type_code in ("deduction", "tax", "employer_contribution")
            item.setCheckState(
                Qt.CheckState.Checked if pre_check else Qt.CheckState.Unchecked
            )
            self._component_list.addItem(item)
        card.layout().addWidget(self._component_list, 1)

        grid = QGridLayout()
        self._assign_effective_from_edit = QDateEdit(card)
        self._assign_effective_from_edit.setCalendarPopup(True)
        self._assign_effective_from_edit.setDisplayFormat("yyyy-MM-dd")
        today = date.today()
        self._assign_effective_from_edit.setDate(QDate(today.year, today.month, 1))
        grid.addWidget(
            create_field_block("Effective From *", self._assign_effective_from_edit),
            0, 0,
        )
        card.layout().addLayout(grid)

        outer.addWidget(card, 1)
        return page

    # --- Review ---
    def _build_review_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Review & Apply")

        self._review_label = QLabel(card)
        self._review_label.setObjectName("DialogSectionSummary")
        self._review_label.setWordWrap(True)
        card.layout().addWidget(self._review_label)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setPlaceholderText("Optional note for the audit trail.")
        self._notes_edit.setFixedHeight(60)
        card.layout().addWidget(create_field_block("Notes", self._notes_edit))

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    # --- Done ---
    def _build_done_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Setup Complete")
        self._done_label = QLabel(card)
        self._done_label.setObjectName("DialogSectionSummary")
        self._done_label.setWordWrap(True)
        card.layout().addWidget(self._done_label)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    # ── Pre-fill ──────────────────────────────────────────────────────

    def _prefill_from_employee(self) -> None:
        emp = self._employee
        if STEP_TAX_CNPS in self._page_index:
            if emp.tax_identifier:
                self._tax_edit.setText(emp.tax_identifier)
            if emp.cnps_number:
                self._cnps_edit.setText(emp.cnps_number)

    # ── Buttons ───────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        self._back_button = QPushButton("Back", self)
        self._back_button.setProperty("variant", "secondary")
        self._back_button.clicked.connect(self._go_back)
        self.button_box.addButton(self._back_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._skip_button = QPushButton("Skip", self)
        self._skip_button.setProperty("variant", "ghost")
        self._skip_button.clicked.connect(self._go_skip)
        self.button_box.addButton(self._skip_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._next_button = QPushButton("Next", self)
        self._next_button.setProperty("variant", "primary")
        self._next_button.clicked.connect(self._go_next)
        self.button_box.addButton(self._next_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._apply_button = QPushButton("Apply", self)
        self._apply_button.setProperty("variant", "primary")
        self._apply_button.clicked.connect(self._handle_apply)
        self.button_box.addButton(self._apply_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._close_button = QPushButton("Cancel", self)
        self._close_button.setProperty("variant", "ghost")
        self._close_button.clicked.connect(self.reject)
        self.button_box.addButton(self._close_button, QDialogButtonBox.ButtonRole.RejectRole)

    # ── Navigation ────────────────────────────────────────────────────

    def _current_key(self) -> str:
        return self._active_steps[self._current_index]

    def _go_next(self) -> None:
        key = self._current_key()
        if key == STEP_COMP and not self._validate_comp():
            return
        if key == STEP_REVIEW:
            self._handle_apply()
            return
        self._current_index += 1
        if self._current_key() == STEP_REVIEW:
            self._refresh_review()
        self._stack.setCurrentIndex(self._page_index[self._current_key()])
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _go_back(self) -> None:
        if self._current_index == 0 or self._committed:
            return
        self._current_index -= 1
        self._skipped.discard(self._current_key())
        self._stack.setCurrentIndex(self._page_index[self._current_key()])
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _go_skip(self) -> None:
        key = self._current_key()
        if key == STEP_COMP:
            # Compensation profile is mandatory.
            self._set_error("A compensation profile is required; please complete this step.")
            return
        self._skipped.add(key)
        self._go_next()

    # ── Validation ────────────────────────────────────────────────────

    def _validate_comp(self) -> bool:
        if STEP_COMP not in self._page_index or STEP_COMP in self._skipped:
            return True
        if not self._profile_name_edit.text().strip():
            self._set_error("Profile name is required.")
            return False
        if self._basic_salary_edit.value() <= 0:
            self._set_error("Basic salary must be greater than zero.")
            return False
        if not self._currency_edit.text().strip():
            self._set_error("Currency is required.")
            return False
        return True

    # ── Review ────────────────────────────────────────────────────────

    def _refresh_review(self) -> None:
        lines: list[str] = [f"<b>Employee:</b> {self._employee.display_name}"]

        if STEP_TAX_CNPS in self._page_index:
            if STEP_TAX_CNPS in self._skipped:
                lines.append("<b>Tax / CNPS:</b> skipped")
            else:
                tax = self._tax_edit.text().strip() or "—"
                cnps = self._cnps_edit.text().strip() or "—"
                lines.append(f"<b>Tax ID:</b> {tax}  ·  <b>CNPS:</b> {cnps}")

        if STEP_PAYMENT in self._page_index:
            if STEP_PAYMENT in self._skipped:
                lines.append("<b>Payment account:</b> skipped")
            else:
                acct_id = self._payment_combo.currentData()
                label = self._payment_combo.currentText() if acct_id else "— None —"
                lines.append(f"<b>Payment account:</b> {label}")

        if STEP_COMP in self._page_index and STEP_COMP not in self._skipped:
            lines.append(
                f"<b>New compensation profile:</b> "
                f"{self._profile_name_edit.text().strip()} · "
                f"{self._basic_salary_edit.value():,.2f} "
                f"{self._currency_edit.text().strip()} · "
                f"from {self._effective_from_edit.date().toString('yyyy-MM-dd')}"
            )

        if STEP_COMPONENTS in self._page_index:
            if STEP_COMPONENTS in self._skipped:
                lines.append("<b>Component assignments:</b> skipped")
            else:
                picks = self._selected_component_ids()
                lines.append(
                    f"<b>Components to assign:</b> {len(picks)} selected "
                    f"(effective from "
                    f"{self._assign_effective_from_edit.date().toString('yyyy-MM-dd')})"
                )

        self._review_label.setText("<br>".join(lines))

    def _selected_component_ids(self) -> list[int]:
        picks: list[int] = []
        for row in range(self._component_list.count()):
            item = self._component_list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                picks.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return picks

    # ── Step pills ────────────────────────────────────────────────────

    def _update_step_pills(self) -> None:
        visible_keys = [k for k in self._active_steps if k != STEP_DONE]
        for pill, key in zip(self._step_pills, visible_keys):
            idx = self._active_steps.index(key)
            if idx < self._current_index:
                pill.setProperty("completed", "true")
                pill.setProperty("current", "false")
            elif idx == self._current_index:
                pill.setProperty("completed", "false")
                pill.setProperty("current", "true")
            else:
                pill.setProperty("completed", "false")
                pill.setProperty("current", "false")
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _update_buttons(self) -> None:
        key = self._current_key()
        on_intro = (key == STEP_INTRO)
        on_review = (key == STEP_REVIEW)
        on_done = (key == STEP_DONE)
        skippable = key in (STEP_TAX_CNPS, STEP_PAYMENT, STEP_COMPONENTS)

        self._back_button.setVisible(not on_intro and not on_done)
        self._skip_button.setVisible(skippable)
        self._next_button.setVisible(not on_review and not on_done)
        self._apply_button.setVisible(on_review)
        self._close_button.setText("Close" if on_done else "Cancel")

    # ── Apply ─────────────────────────────────────────────────────────

    def _set_error(self, msg: str | None) -> None:
        if not msg:
            self._error_label.hide()
            self._error_label.clear()
        else:
            self._error_label.setText(msg)
            self._error_label.show()

    def _handle_apply(self) -> None:
        emp = self._employee

        # 1. Build UpdateEmployeeCommand only if tax/payment changed.
        new_tax = emp.tax_identifier
        new_cnps = emp.cnps_number
        new_pay = emp.default_payment_account_id
        tax_changed = False
        cnps_changed = False
        payment_changed = False

        if STEP_TAX_CNPS in self._page_index and STEP_TAX_CNPS not in self._skipped:
            typed_tax = self._tax_edit.text().strip() or None
            typed_cnps = self._cnps_edit.text().strip() or None
            if typed_tax != emp.tax_identifier:
                new_tax = typed_tax
                tax_changed = True
            if typed_cnps != emp.cnps_number:
                new_cnps = typed_cnps
                cnps_changed = True

        if STEP_PAYMENT in self._page_index and STEP_PAYMENT not in self._skipped:
            typed_pay = self._payment_combo.currentData()
            if typed_pay != emp.default_payment_account_id:
                new_pay = typed_pay
                payment_changed = True

        updated_employee = False
        if tax_changed or cnps_changed or payment_changed:
            try:
                self._registry.employee_service.update_employee(
                    self._company_id, emp.id,
                    UpdateEmployeeCommand(
                        employee_number=emp.employee_number,
                        display_name=emp.display_name,
                        first_name=emp.first_name,
                        last_name=emp.last_name,
                        hire_date=emp.hire_date,
                        base_currency_code=emp.base_currency_code,
                        is_active=emp.is_active,
                        department_id=emp.department_id,
                        position_id=emp.position_id,
                        termination_date=emp.termination_date,
                        phone=emp.phone,
                        email=emp.email,
                        tax_identifier=new_tax,
                        cnps_number=new_cnps,
                        default_payment_account_id=new_pay,
                    ),
                )
                updated_employee = True
            except (ValidationError, ConflictError, NotFoundError,
                    PermissionDeniedError) as exc:
                self._set_error(str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                _log.exception("Employee update failed")
                self._set_error(f"Unexpected error: {exc}")
                return

        # 2. Compensation profile
        profile_id: int | None = None
        if STEP_COMP in self._page_index and STEP_COMP not in self._skipped:
            try:
                profile = self._registry.compensation_profile_service.create_profile(
                    self._company_id,
                    CreateCompensationProfileCommand(
                        employee_id=emp.id,
                        profile_name=self._profile_name_edit.text().strip(),
                        basic_salary=Decimal(str(self._basic_salary_edit.value())),
                        currency_code=self._currency_edit.text().strip().upper(),
                        effective_from=self._effective_from_edit.date().toPython(),
                    ),
                )
                profile_id = profile.id
            except (ValidationError, ConflictError, NotFoundError,
                    PermissionDeniedError) as exc:
                self._set_error(f"Compensation profile: {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                _log.exception("Compensation profile create failed")
                self._set_error(f"Unexpected error: {exc}")
                return

        # 3. Component assignments
        assignment_ids: list[int] = []
        assignment_errors: list[str] = []
        if STEP_COMPONENTS in self._page_index and STEP_COMPONENTS not in self._skipped:
            eff_from = self._assign_effective_from_edit.date().toPython()
            for cid in self._selected_component_ids():
                try:
                    a = self._registry.component_assignment_service.create_assignment(
                        self._company_id,
                        CreateComponentAssignmentCommand(
                            employee_id=emp.id,
                            component_id=cid,
                            effective_from=eff_from,
                        ),
                    )
                    assignment_ids.append(a.id)
                except (ValidationError, ConflictError, NotFoundError,
                        PermissionDeniedError) as exc:
                    assignment_errors.append(f"Component {cid}: {exc}")

        # 4. Build result
        skipped_gaps = tuple(sorted(self._skipped))
        summary_lines: list[str] = [f"Payroll setup applied for {emp.display_name}."]
        if updated_employee:
            bits = []
            if tax_changed:
                bits.append("tax identifier")
            if cnps_changed:
                bits.append("CNPS number")
            if payment_changed:
                bits.append("payment account")
            summary_lines.append(f"- Updated: {', '.join(bits)}")
        if profile_id is not None:
            summary_lines.append(
                f"- Created compensation profile (id={profile_id})"
            )
        if assignment_ids:
            summary_lines.append(
                f"- Created {len(assignment_ids)} component assignment(s)"
            )
        if skipped_gaps:
            summary_lines.append(
                f"- Skipped: {', '.join(_STEP_LABELS.get(s, s) for s in skipped_gaps)}"
            )
        if assignment_errors:
            summary_lines.append("- Assignment warnings:")
            summary_lines.extend(f"    · {e}" for e in assignment_errors)

        summary = "\n".join(summary_lines)

        self._result = EmployeePayrollSetupResult(
            employee_id=emp.id,
            updated_employee=updated_employee,
            tax_identifier_set=tax_changed,
            cnps_number_set=cnps_changed,
            payment_account_set=payment_changed,
            compensation_profile_id=profile_id,
            assignment_ids=tuple(assignment_ids),
            skipped_gaps=skipped_gaps,
            summary=summary,
        )
        self._committed = True

        self._done_label.setText(summary.replace("\n", "<br>"))
        self._current_index = self._active_steps.index(STEP_DONE)
        self._stack.setCurrentIndex(self._page_index[STEP_DONE])
        self._update_step_pills()
        self._update_buttons()
