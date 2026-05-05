# -*- coding: utf-8 -*-
"""Rewrite script for CompensationChangeWizardDialog -> WizardShell migration."""
import pathlib

TARGET = pathlib.Path(
    "src/seeker_accounting/modules/payroll/ui/wizards/compensation_change_wizard.py"
)

old_text = TARGET.read_text(encoding="utf-8")

# ── Keep the file header (module docstring + imports + dataclass + step IDs
#    + module-level _card helper) and replace everything from the class onwards.
# We detect the split point at the line that begins with "class ".
lines = old_text.splitlines(keepends=True)
split_idx = next(
    i for i, l in enumerate(lines) if l.startswith("class CompensationChangeWizardDialog")
)
# Include the preceding blank line in what we replace.
if split_idx > 0 and lines[split_idx - 1].strip() == "":
    split_idx -= 1

header = "".join(lines[:split_idx])

new_class = """\


# ── Dialog ────────────────────────────────────────────────────────────────────


class CompensationChangeWizardDialog(WizardShell):
    \"\"\"4-step guided compensation change wizard — P4.S5, built on WizardShell.\"\"\"

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
        self._result: CompensationChangeWizardResult | None = None

        super().__init__(
            f"Compensation Change \\u2014 {company_name}",
            _STEPS,
            parent=parent,
            finish_label="Apply Change",
            min_width=820,
            min_height=620,
        )
        self.setObjectName("CompensationChangeWizardDialog")

        self._employee_widget = self._build_employee_step()
        self._comp_widget = self._build_comp_step()
        self._recurring_widget = self._build_recurring_step()
        self._review_widget = self._build_review_step()

        self.set_step_widget(_STEP_EMPLOYEE, self._employee_widget)
        self.set_step_widget(_STEP_COMP, self._comp_widget)
        self.set_step_widget(_STEP_RECURRING, self._recurring_widget)
        self.set_step_widget(_STEP_REVIEW, self._review_widget)

        self.next_requested.connect(self._on_next)
        self.back_requested.connect(self._on_back)
        self.finish_requested.connect(self._on_finish)
        self.cancel_requested.connect(self.reject)

        self._load_employees()
        self._load_components()

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
            service_registry,
            company_id,
            company_name,
            employee_id=employee_id,
            parent=parent,
        )
        dialog.exec()
        return dialog.result_payload

    # ── Step widget builders ──────────────────────────────────────────

    def _build_employee_step(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        card = _card(w, "Employee & Effective Date")
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
        return w

    def _build_comp_step(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        card = _card(w, "New Compensation Profile")

        self._comp_current_label = QLabel(card)
        self._comp_current_label.setObjectName("DialogSectionSummary")
        self._comp_current_label.setWordWrap(True)
        card.layout().addWidget(self._comp_current_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._profile_name_edit = QLineEdit(card)
        self._profile_name_edit.setPlaceholderText("e.g. 2026 Salary Adjustment")
        grid.addWidget(
            create_field_block("Profile Name *", self._profile_name_edit), 0, 0, 1, 2
        )

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
        return w

    def _build_recurring_step(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        card_current = _card(w, "Current Recurring Components")
        self._recurring_table = QTableWidget(0, 4, card_current)
        self._recurring_table.setHorizontalHeaderLabels(
            ["Component", "Override Amount", "Override Rate", "Active"]
        )
        self._recurring_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._recurring_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._recurring_table.verticalHeader().setVisible(False)
        self._recurring_table.horizontalHeader().setStretchLastSection(True)
        self._recurring_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        card_current.layout().addWidget(self._recurring_table, 1)
        outer.addWidget(card_current, 1)

        card_add = _card(w, "Add Recurring Component (Optional)")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._component_combo = QComboBox(card_add)
        self._component_combo.setMinimumWidth(260)
        self._component_combo.addItem("\\u2014 Skip \\u2014", None)
        grid.addWidget(
            create_field_block("Component", self._component_combo), 0, 0, 1, 2
        )

        self._override_amount_edit = QLineEdit(card_add)
        self._override_amount_edit.setPlaceholderText("blank = use component default")
        grid.addWidget(
            create_field_block("Override Amount", self._override_amount_edit), 1, 0
        )

        self._override_rate_edit = QLineEdit(card_add)
        self._override_rate_edit.setPlaceholderText("blank = use component default")
        grid.addWidget(
            create_field_block("Override Rate", self._override_rate_edit), 1, 1
        )

        card_add.layout().addLayout(grid)

        hint = QLabel(
            "Only one component may be added per wizard run. For multiple "
            "changes, run the wizard again or use the Component Assignment dialog.",
            card_add,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card_add.layout().addWidget(hint)

        outer.addWidget(card_add)
        return w

    def _build_review_step(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        card = _card(w, "Review & Confirm")

        self._review_label = QLabel(card)
        self._review_label.setObjectName("DialogSectionSummary")
        self._review_label.setWordWrap(True)
        card.layout().addWidget(self._review_label)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setPlaceholderText(
            "Optional approval / change note (recorded with the new profile)."
        )
        self._notes_edit.setFixedHeight(96)
        card.layout().addWidget(create_field_block("Approval Note", self._notes_edit))

        outer.addWidget(card)
        outer.addStretch(1)
        return w

    # ── Navigation handlers ───────────────────────────────────────────

    def _on_next(self, step_id: str) -> None:
        if step_id == _STEP_EMPLOYEE:
            issues = self._validate_employee_step()
            if issues:
                self.set_step_issues(_STEP_EMPLOYEE, issues)
                return
            self.set_step_issues(_STEP_EMPLOYEE, [])
            self._refresh_comp_page()
            self.advance_step()

        elif step_id == _STEP_COMP:
            issues = self._validate_comp_step()
            if issues:
                self.set_step_issues(_STEP_COMP, issues)
                return
            self.set_step_issues(_STEP_COMP, [])
            self._refresh_recurring_page()
            self.advance_step()

        elif step_id == _STEP_RECURRING:
            issues = self._validate_recurring_step()
            if issues:
                self.set_step_issues(_STEP_RECURRING, issues)
                return
            self.set_step_issues(_STEP_RECURRING, [])
            self._refresh_review()
            self.advance_step()

    def _on_back(self, step_id: str) -> None:
        self.go_back()

    def _on_finish(self) -> None:
        self._apply_change()

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
        self._employee_combo.addItem("\\u2014 Select Employee \\u2014", None)
        for e in rows:
            self._employee_combo.addItem(
                f"{e.employee_number}  \\u00b7  {e.display_name}", e.id
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
        self._component_combo.addItem("\\u2014 Skip \\u2014", None)
        for c in self._components:
            self._component_combo.addItem(
                f"{c.component_code}  \\u00b7  {c.component_name}", c.id
            )

    # ── Employee helpers ──────────────────────────────────────────────

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
                f"<b>Current profile:</b> {self._current_profile.profile_name} "
                f"\\u2014 {self._current_profile.basic_salary} "
                f"{self._current_profile.currency_code} (from "
                f"{self._current_profile.effective_from.isoformat()})"
            )
            self._currency_edit.setText(self._current_profile.currency_code)
        else:
            self._current_label.setText(
                "<i>No active compensation profile on record.</i>"
            )
            self._currency_edit.setText("XAF")

    # ── Page refresh ──────────────────────────────────────────────────

    def _refresh_comp_page(self) -> None:
        if self._current_profile:
            self._comp_current_label.setText(
                f"<b>Replacing:</b> {self._current_profile.profile_name} "
                f"\\u2014 {self._current_profile.basic_salary} "
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
                i, 0, QTableWidgetItem(f"{a.component_code} \\u00b7 {a.component_name}")
            )
            self._recurring_table.setItem(
                i, 1,
                QTableWidgetItem(
                    str(a.override_amount) if a.override_amount is not None else "\\u2014"
                ),
            )
            self._recurring_table.setItem(
                i, 2,
                QTableWidgetItem(
                    str(a.override_rate) if a.override_rate is not None else "\\u2014"
                ),
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
        comp_label = self._component_combo.currentText() if comp_id else "\\u2014 none \\u2014"

        current_line = "No active profile"
        if self._current_profile:
            current_line = (
                f"{self._current_profile.profile_name} \\u2014 "
                f"{self._current_profile.basic_salary} {self._current_profile.currency_code}"
            )

        self._review_label.setText(
            f"<b>Employee:</b> {emp.display_name if emp else '\\u2014'}<br>"
            f"<b>Effective from:</b> {eff.isoformat()}<br>"
            f"<b>Current:</b> {current_line}<br>"
            f"<b>New:</b> {self._profile_name_edit.text().strip() or '(unnamed)'} "
            f"\\u2014 {salary_text} {currency}<br>"
            f"<b>Component add:</b> {comp_label}<br><br>"
            f"<i>This change will be picked up by the next payroll run "
            f"for periods starting on or after the effective date.</i>"
        )

    # ── Validation ────────────────────────────────────────────────────

    def _validate_employee_step(self) -> list[ValidationIssue]:
        if self._selected_employee_id() is None:
            return [ValidationIssue(severity="error", message="Select an employee.")]
        return []

    def _validate_comp_step(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not self._profile_name_edit.text().strip():
            issues.append(
                ValidationIssue(severity="error", message="Profile name is required.")
            )
        try:
            salary = Decimal(self._salary_edit.text().strip())
            if salary <= 0:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        message="New basic salary must be greater than zero.",
                    )
                )
        except InvalidOperation:
            issues.append(
                ValidationIssue(severity="error", message="New basic salary must be a number.")
            )
        if not self._currency_edit.text().strip():
            issues.append(ValidationIssue(severity="error", message="Currency is required."))
        return issues

    def _validate_recurring_step(self) -> list[ValidationIssue]:
        if self._component_combo.currentData() is None:
            return []
        issues: list[ValidationIssue] = []
        for text, label in (
            (self._override_amount_edit.text().strip(), "Override amount"),
            (self._override_rate_edit.text().strip(), "Override rate"),
        ):
            if not text:
                continue
            try:
                Decimal(text)
            except InvalidOperation:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        message=f"{label} must be a number (or blank).",
                    )
                )
        return issues

    # ── Apply ─────────────────────────────────────────────────────────

    def _apply_change(self) -> None:
        emp = self._selected_employee()
        if emp is None:
            self.set_step_issues(
                _STEP_REVIEW,
                [ValidationIssue(severity="error", message="Employee not selected.")],
            )
            return

        effective_from = self._effective_edit.date().toPython()
        salary_val = _parse_decimal(self._salary_edit.text())
        if salary_val is None or salary_val <= 0:
            self.set_step_issues(
                _STEP_REVIEW,
                [ValidationIssue(severity="error", message="New basic salary is invalid.")],
            )
            return

        currency = self._currency_edit.text().strip().upper()
        profile_name = self._profile_name_edit.text().strip()
        notes = self._notes_edit.toPlainText().strip() or None

        self.set_status_text("Applying change...")
        try:
            profile_dto = self._registry.compensation_profile_service.create_profile(
                self._company_id,
                CreateCompensationProfileCommand(
                    employee_id=emp.id,
                    profile_name=profile_name,
                    basic_salary=salary_val,
                    currency_code=currency,
                    effective_from=effective_from,
                    notes=notes,
                ),
            )
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
            self.set_step_issues(
                _STEP_REVIEW, [ValidationIssue(severity="error", message=str(exc))]
            )
            self.set_status_text("")
            return
        except Exception as exc:  # noqa: BLE001
            _log.exception("Compensation change failed")
            self.set_step_issues(
                _STEP_REVIEW,
                [ValidationIssue(severity="error", message=f"Unexpected error: {exc}")],
            )
            self.set_status_text("")
            return

        new_assignment_ids: list[int] = []
        comp_id = self._component_combo.currentData()
        if isinstance(comp_id, int):
            override_amount = _parse_decimal(self._override_amount_edit.text())
            override_rate = _parse_decimal(self._override_rate_edit.text())
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
                new_assignment_ids.append(assignment.id)
            except (
                ValidationError,
                ConflictError,
                NotFoundError,
                PermissionDeniedError,
            ) as exc:
                # Profile was created; surface component failure as warning.
                self.set_step_issues(
                    _STEP_REVIEW,
                    [
                        ValidationIssue(
                            severity="warning",
                            message=(
                                f"Profile created but component assignment failed: {exc}"
                            ),
                        )
                    ],
                )

        summary = (
            f"Compensation change applied for {emp.display_name}.\\n"
            f"New profile: {profile_dto.profile_name} \\u2014 "
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
            new_assignment_ids=tuple(new_assignment_ids),
            notes=notes,
            summary=summary,
        )
        self.set_status_text("Change applied.")
        self.accept()


def _parse_decimal(text: str) -> "Decimal | None":
    t = text.strip()
    if not t:
        return None
    try:
        return Decimal(t)
    except InvalidOperation:
        return None
"""

# Process unicode escapes in the new class
import re
def unescape(s):
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)

new_class_processed = unescape(new_class)
new_content = header + new_class_processed

TARGET.write_text(new_content, encoding="utf-8")
print(f"Written {len(new_content)} chars, {len(new_content.splitlines())} lines")
