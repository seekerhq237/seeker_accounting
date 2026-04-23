"""CompensationChangeWizardDialog — guided compensation change flow.

Orchestrates the salary/profile + recurring-component change lifecycle
for a single employee. Expert controls (`Edit Compensation`,
`Assign Component`) remain available on the ribbon as fast-path
alternatives.

Steps:

1. **Employee**  — pick employee + effective date for the change.
2. **New Comp**  — new compensation profile (name, basic salary,
                   currency). Shows current active profile for context.
3. **Recurring** — optionally add a recurring-component assignment
                   effective from the same date. Shows current
                   recurring assignments for context.
4. **Review**    — confirm changes + optional approval note, then save.

First-pass scope:
- A live retro / next-run preview is **not** included. The blueprint
  flags this as a future service addition (see plan P7a further
  consideration #1). This wizard creates effective-dated records which
  will be picked up naturally by the next payroll run for the period.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
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
class CompensationChangeWizardResult:
    employee_id: int
    employee_display_name: str
    effective_from: date
    profile_id: int
    profile_name: str
    new_basic_salary: Decimal
    currency_code: str
    new_assignment_ids: tuple[int, ...] = field(default_factory=tuple)
    notes: str | None = None
    summary: str = ""


class CompensationChangeWizardDialog(BaseDialog):
    """4-step guided compensation change dialog — see module docstring."""

    _STEP_LABELS = (
        "1. Employee",
        "2. New Compensation",
        "3. Recurring Components",
        "4. Review",
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        employee_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._preselected_employee_id = employee_id

        self._employees: list = []
        self._components: list = []
        self._current_profile = None
        self._current_assignments: list = []
        self._created_profile = None
        self._new_assignment_ids: list[int] = []
        self._result: CompensationChangeWizardResult | None = None
        self._current_step = 0

        super().__init__(
            "Compensation Change",
            parent,
            help_key="wizard.compensation_change",
        )
        self.setObjectName("CompensationChangeWizardDialog")
        self.resize(820, 660)

        intro = QLabel(
            "Record a salary / profile change and (optionally) add recurring "
            "components for an employee. Effective-dated — the next payroll "
            "run for the period will pick up the new values.",
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
        self._load_employees()
        self._load_components()
        self._update_step_pills()
        self._update_buttons()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def result_payload(self) -> CompensationChangeWizardResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        employee_id: int | None = None,
        parent: QWidget | None = None,
    ) -> CompensationChangeWizardResult | None:
        dialog = cls(
            service_registry, company_id, company_name,
            employee_id=employee_id, parent=parent,
        )
        dialog.exec()
        return dialog.result_payload

    # ── Header ────────────────────────────────────────────────────────

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
        self._stack.addWidget(self._build_employee_page())
        self._stack.addWidget(self._build_comp_page())
        self._stack.addWidget(self._build_recurring_page())
        self._stack.addWidget(self._build_review_page())
        self._stack.addWidget(self._build_done_page())
        return self._stack

    def _build_employee_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Employee & Effective Date")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._employee_combo = QComboBox(card)
        self._employee_combo.setMinimumWidth(300)
        self._employee_combo.currentIndexChanged.connect(self._on_employee_changed)
        grid.addWidget(create_field_block("Employee *", self._employee_combo), 0, 0, 1, 2)

        today = date.today()
        self._effective_edit = QDateEdit(card)
        self._effective_edit.setCalendarPopup(True)
        self._effective_edit.setDisplayFormat("yyyy-MM-dd")
        self._effective_edit.setDate(QDate(today.year, today.month, today.day))
        grid.addWidget(create_field_block("Effective From *", self._effective_edit), 1, 0)

        card.layout().addLayout(grid)

        self._current_label = QLabel(card)
        self._current_label.setObjectName("DialogSectionSummary")
        self._current_label.setWordWrap(True)
        card.layout().addWidget(self._current_label)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_comp_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("New Compensation Profile")

        self._comp_current_label = QLabel(card)
        self._comp_current_label.setObjectName("DialogSectionSummary")
        self._comp_current_label.setWordWrap(True)
        card.layout().addWidget(self._comp_current_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._profile_name_edit = QLineEdit(card)
        self._profile_name_edit.setPlaceholderText("e.g. 2026 Salary Adjustment")
        grid.addWidget(create_field_block("Profile Name *", self._profile_name_edit), 0, 0, 1, 2)

        self._salary_edit = QLineEdit(card)
        self._salary_edit.setPlaceholderText("0.00")
        grid.addWidget(create_field_block("New Basic Salary *", self._salary_edit), 1, 0)

        self._currency_edit = QLineEdit(card)
        self._currency_edit.setMaxLength(3)
        self._currency_edit.setPlaceholderText("XAF")
        grid.addWidget(create_field_block("Currency *", self._currency_edit), 1, 1)

        card.layout().addLayout(grid)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_recurring_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card_current = self._card("Current Recurring Components")
        self._recurring_table = QTableWidget(0, 4, card_current)
        self._recurring_table.setHorizontalHeaderLabels(
            ["Component", "Override Amount", "Override Rate", "Active"]
        )
        self._recurring_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._recurring_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._recurring_table.verticalHeader().setVisible(False)
        self._recurring_table.horizontalHeader().setStretchLastSection(True)
        self._recurring_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        card_current.layout().addWidget(self._recurring_table, 1)
        outer.addWidget(card_current, 1)

        card_add = self._card("Add Recurring Component (Optional)")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._component_combo = QComboBox(card_add)
        self._component_combo.setMinimumWidth(260)
        self._component_combo.addItem("— Skip —", None)
        grid.addWidget(create_field_block("Component", self._component_combo), 0, 0, 1, 2)

        self._override_amount_edit = QLineEdit(card_add)
        self._override_amount_edit.setPlaceholderText("blank = use component default")
        grid.addWidget(create_field_block("Override Amount", self._override_amount_edit), 1, 0)

        self._override_rate_edit = QLineEdit(card_add)
        self._override_rate_edit.setPlaceholderText("blank = use component default")
        grid.addWidget(create_field_block("Override Rate", self._override_rate_edit), 1, 1)

        card_add.layout().addLayout(grid)

        hint = QLabel(
            "Only one component may be added from this wizard. For multiple "
            "changes, run the wizard again or use the Component Assignment "
            "dialog.",
            card_add,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card_add.layout().addWidget(hint)

        outer.addWidget(card_add)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        card = self._card("Review & Confirm")
        self._review_label = QLabel(card)
        self._review_label.setObjectName("DialogSectionSummary")
        self._review_label.setWordWrap(True)
        card.layout().addWidget(self._review_label)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setPlaceholderText(
            "Optional approval / change note (recorded with the new profile)."
        )
        self._notes_edit.setFixedHeight(96)
        card.layout().addWidget(
            create_field_block("Approval Note", self._notes_edit)
        )

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Compensation Change Applied")
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

        self._apply_button = QPushButton("Apply Change", self)
        self._apply_button.setProperty("variant", "primary")
        self._apply_button.clicked.connect(self._handle_apply)
        self.button_box.addButton(self._apply_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._close_button = QPushButton("Cancel", self)
        self._close_button.setProperty("variant", "ghost")
        self._close_button.clicked.connect(self.reject)
        self.button_box.addButton(self._close_button, QDialogButtonBox.ButtonRole.RejectRole)

    # ── Data loading ──────────────────────────────────────────────────

    def _load_employees(self) -> None:
        try:
            rows = self._registry.employee_service.list_employees(
                self._company_id, active_only=True
            )
        except Exception:  # noqa: BLE001
            _log.warning("Employee load error", exc_info=True)
            rows = []
        self._employees = rows
        self._employee_combo.blockSignals(True)
        self._employee_combo.clear()
        self._employee_combo.addItem("— Select Employee —", None)
        for e in rows:
            self._employee_combo.addItem(
                f"{e.employee_number}  ·  {e.display_name}", e.id
            )
        self._employee_combo.blockSignals(False)

        if self._preselected_employee_id is not None:
            idx = self._employee_combo.findData(self._preselected_employee_id)
            if idx >= 0:
                self._employee_combo.setCurrentIndex(idx)

    def _load_components(self) -> None:
        try:
            self._components = self._registry.payroll_component_service.list_components(
                self._company_id, active_only=True
            )
        except Exception:  # noqa: BLE001
            _log.warning("Component load error", exc_info=True)
            self._components = []
        self._component_combo.clear()
        self._component_combo.addItem("— Skip —", None)
        for c in self._components:
            self._component_combo.addItem(
                f"{c.component_code}  ·  {c.component_name}", c.id
            )

    def _selected_employee_id(self) -> int | None:
        data = self._employee_combo.currentData()
        return data if isinstance(data, int) else None

    def _selected_employee(self):
        eid = self._selected_employee_id()
        if eid is None:
            return None
        for e in self._employees:
            if e.id == eid:
                return e
        return None

    def _on_employee_changed(self) -> None:
        emp = self._selected_employee()
        if emp is None:
            self._current_profile = None
            self._current_assignments = []
            self._current_label.setText("")
            return
        try:
            profiles = self._registry.compensation_profile_service.list_profiles(
                self._company_id, employee_id=emp.id, active_only=True
            )
        except Exception:  # noqa: BLE001
            profiles = []
        self._current_profile = profiles[0] if profiles else None

        try:
            assignments = self._registry.component_assignment_service.list_assignments(
                self._company_id, employee_id=emp.id, active_only=True
            )
        except Exception:  # noqa: BLE001
            assignments = []
        self._current_assignments = assignments

        if self._current_profile:
            self._current_label.setText(
                f"<b>Current profile:</b> {self._current_profile.profile_name} — "
                f"{self._current_profile.basic_salary} "
                f"{self._current_profile.currency_code} (from "
                f"{self._current_profile.effective_from.isoformat()})"
            )
            # Pre-populate currency on the next page from the current one.
            self._currency_edit.setText(self._current_profile.currency_code)
        else:
            self._current_label.setText(
                "<i>No active compensation profile on record.</i>"
            )
            self._currency_edit.setText("XAF")

    # ── Navigation ────────────────────────────────────────────────────

    def _go_next(self) -> None:
        if self._current_step == 0 and not self._validate_employee():
            return
        if self._current_step == 1 and not self._validate_comp():
            return
        if self._current_step == 2 and not self._validate_recurring():
            return
        if self._current_step == 3:  # review → apply
            self._handle_apply()
            return

        self._current_step += 1
        # Refresh each entered page as we advance.
        if self._current_step == 1:
            self._refresh_comp_page()
        elif self._current_step == 2:
            self._refresh_recurring_page()
        elif self._current_step == 3:
            self._refresh_review()
        self._stack.setCurrentIndex(self._current_step)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _go_back(self) -> None:
        if self._current_step <= 0:
            return
        # Block going back past apply once the profile is saved.
        if self._created_profile is not None:
            self._set_error(
                "Change already applied. Use Cancel to close; the new profile "
                "is visible on the Compensation Profiles tab."
            )
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
        on_review = self._current_step == 3
        on_done = self._current_step == 4

        self._back_button.setVisible(self._current_step > 0 and not on_done)
        self._next_button.setVisible(not on_review and not on_done)
        self._apply_button.setVisible(on_review)
        self._close_button.setText("Close" if on_done else "Cancel")

    def _set_error(self, msg: str | None) -> None:
        if not msg:
            self._error_label.hide()
            self._error_label.clear()
            return
        self._error_label.setText(msg)
        self._error_label.show()

    # ── Page refresh ──────────────────────────────────────────────────

    def _refresh_comp_page(self) -> None:
        if self._current_profile:
            self._comp_current_label.setText(
                f"<b>Replacing:</b> {self._current_profile.profile_name} — "
                f"{self._current_profile.basic_salary} "
                f"{self._current_profile.currency_code}"
            )
        else:
            self._comp_current_label.setText(
                "<i>Creating a first compensation profile for this employee.</i>"
            )

    def _refresh_recurring_page(self) -> None:
        rows = self._current_assignments
        self._recurring_table.setRowCount(len(rows))
        for i, a in enumerate(rows):
            self._recurring_table.setItem(
                i, 0, QTableWidgetItem(f"{a.component_code} · {a.component_name}")
            )
            self._recurring_table.setItem(
                i, 1,
                QTableWidgetItem(str(a.override_amount) if a.override_amount is not None else "—"),
            )
            self._recurring_table.setItem(
                i, 2,
                QTableWidgetItem(str(a.override_rate) if a.override_rate is not None else "—"),
            )
            self._recurring_table.setItem(
                i, 3, QTableWidgetItem("Yes" if a.is_active else "No")
            )
        if not rows:
            self._recurring_table.setRowCount(1)
            placeholder = QTableWidgetItem("No recurring components on record.")
            placeholder.setForeground(Qt.GlobalColor.gray)
            self._recurring_table.setItem(0, 0, placeholder)
            self._recurring_table.setSpan(0, 0, 1, 4)

    def _refresh_review(self) -> None:
        emp = self._selected_employee()
        eff = self._effective_edit.date().toPython()
        salary_text = self._salary_edit.text().strip() or "(invalid)"
        currency = self._currency_edit.text().strip().upper() or "XAF"
        comp_id = self._component_combo.currentData()
        comp_label = self._component_combo.currentText() if comp_id else "— none —"

        current_line = "No active profile"
        if self._current_profile:
            current_line = (
                f"{self._current_profile.profile_name} — "
                f"{self._current_profile.basic_salary} "
                f"{self._current_profile.currency_code}"
            )

        self._review_label.setText(
            f"<b>Employee:</b> {emp.display_name if emp else '—'}<br>"
            f"<b>Effective from:</b> {eff.isoformat()}<br>"
            f"<b>Current:</b> {current_line}<br>"
            f"<b>New:</b> {self._profile_name_edit.text().strip() or '(unnamed)'} "
            f"— {salary_text} {currency}<br>"
            f"<b>Recurring component add:</b> {comp_label}<br><br>"
            f"<i>Note: this change will be picked up by the next payroll run "
            f"whose period starts on or after the effective date.</i>"
        )

    # ── Validation ────────────────────────────────────────────────────

    def _validate_employee(self) -> bool:
        if self._selected_employee_id() is None:
            self._set_error("Select an employee.")
            return False
        return True

    def _validate_comp(self) -> bool:
        if not self._profile_name_edit.text().strip():
            self._set_error("Profile name is required.")
            return False
        try:
            salary = Decimal(self._salary_edit.text().strip())
        except InvalidOperation:
            self._set_error("New basic salary must be a number.")
            return False
        if salary <= 0:
            self._set_error("New basic salary must be greater than zero.")
            return False
        if not self._currency_edit.text().strip():
            self._set_error("Currency is required.")
            return False
        return True

    def _validate_recurring(self) -> bool:
        # Component add is optional. If chosen, override fields must be
        # numeric (or blank).
        if self._component_combo.currentData() is None:
            return True
        for text, label in (
            (self._override_amount_edit.text().strip(), "Override amount"),
            (self._override_rate_edit.text().strip(), "Override rate"),
        ):
            if not text:
                continue
            try:
                Decimal(text)
            except InvalidOperation:
                self._set_error(f"{label} must be a number (or blank).")
                return False
        return True

    # ── Apply ─────────────────────────────────────────────────────────

    def _handle_apply(self) -> None:
        emp = self._selected_employee()
        if emp is None:
            self._set_error("Select an employee.")
            return
        effective_from = self._effective_edit.date().toPython()
        try:
            salary = Decimal(self._salary_edit.text().strip())
        except InvalidOperation:
            self._set_error("New basic salary must be a number.")
            return
        currency = self._currency_edit.text().strip().upper()
        profile_name = self._profile_name_edit.text().strip()
        notes = self._notes_edit.toPlainText().strip() or None

        try:
            profile_dto = self._registry.compensation_profile_service.create_profile(
                self._company_id,
                CreateCompensationProfileCommand(
                    employee_id=emp.id,
                    profile_name=profile_name,
                    basic_salary=salary,
                    currency_code=currency,
                    effective_from=effective_from,
                    notes=notes,
                ),
            )
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
            self._set_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            _log.exception("Compensation change failed")
            self._set_error(f"Unexpected error: {exc}")
            return

        self._created_profile = profile_dto

        # Optional recurring component add
        comp_id = self._component_combo.currentData()
        if isinstance(comp_id, int):
            override_amount = self._parse_optional_decimal(
                self._override_amount_edit.text()
            )
            override_rate = self._parse_optional_decimal(
                self._override_rate_edit.text()
            )
            try:
                assignment = self._registry.component_assignment_service.create_assignment(
                    self._company_id,
                    CreateComponentAssignmentCommand(
                        employee_id=emp.id,
                        component_id=comp_id,
                        effective_from=effective_from,
                        override_amount=override_amount,
                        override_rate=override_rate,
                    ),
                )
                self._new_assignment_ids.append(assignment.id)
            except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
                # Profile was created; surface the assignment error but
                # still treat the profile change as applied.
                self._set_error(
                    f"Profile created but recurring component assignment failed: {exc}"
                )

        summary = (
            f"Compensation change applied for {emp.display_name}.\n"
            f"New profile: {profile_dto.profile_name} — "
            f"{profile_dto.basic_salary} {profile_dto.currency_code} "
            f"(effective {effective_from.isoformat()})."
        )
        self._result = CompensationChangeWizardResult(
            employee_id=emp.id,
            employee_display_name=emp.display_name,
            effective_from=effective_from,
            profile_id=profile_dto.id,
            profile_name=profile_dto.profile_name,
            new_basic_salary=profile_dto.basic_salary,
            currency_code=profile_dto.currency_code,
            new_assignment_ids=tuple(self._new_assignment_ids),
            notes=notes,
            summary=summary,
        )
        self._done_label.setText(summary.replace("\n", "<br>"))
        self._current_step = 4
        self._stack.setCurrentIndex(4)
        self._update_step_pills()
        self._update_buttons()

    @staticmethod
    def _parse_optional_decimal(text: str) -> Decimal | None:
        text = text.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
