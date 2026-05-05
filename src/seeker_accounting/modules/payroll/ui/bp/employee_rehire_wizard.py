"""RehireEmployeeWizardDialog — P4.S6 Rehire Business Process.

3-step WizardShell workflow:

1. **Confirm** — shows the inactive employee's details.
2. **Terms**   — captures the new hire date.
3. **Review**  — summary + confirmation before the service call.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Sequence

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.employee_dto import (
    EmployeeListItemDTO,
    RehireEmployeeCommand,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.components.wizard_shell import (
    ValidationIssue,
    WizardShell,
    WizardStepDescriptor,
)

_log = logging.getLogger(__name__)

_STEP_CONFIRM = "confirm"
_STEP_TERMS = "terms"
_STEP_REVIEW = "review"

_STEPS: Sequence[WizardStepDescriptor] = (
    WizardStepDescriptor(id=_STEP_CONFIRM, title="Confirm Employee",
                         description="Verify the employee you are rehiring."),
    WizardStepDescriptor(id=_STEP_TERMS, title="Rehire Terms",
                         description="New hire date and options."),
    WizardStepDescriptor(id=_STEP_REVIEW, title="Review & Apply",
                         description="Summary before finalising the rehire."),
)


def _card(parent: QWidget, title: str) -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName("WizardCard")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 12, 16, 12)
    lay.setSpacing(8)
    if title:
        hdr = QLabel(f"<b>{title}</b>", frame)
        hdr.setObjectName("WizardCardHeader")
        lay.addWidget(hdr)
    return frame


class RehireEmployeeWizardDialog(WizardShell):
    """Guided 3-step rehire wizard."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        employee: EmployeeListItemDTO,
        parent: QWidget | None = None,
    ) -> None:
        self._registry = service_registry
        self._company_id = company_id
        self._employee = employee
        self._success = False

        super().__init__(
            f"Rehire Employee \u2014 {employee.display_name}",
            _STEPS,
            parent=parent,
            finish_label="Confirm Rehire",
            min_width=620,
            min_height=480,
        )
        self.setObjectName("RehireEmployeeWizardDialog")

        self.set_step_widget(_STEP_CONFIRM, self._build_confirm_step())
        self.set_step_widget(_STEP_TERMS, self._build_terms_step())
        self.set_step_widget(_STEP_REVIEW, self._build_review_step())

        self.next_requested.connect(self._on_next)
        self.back_requested.connect(self._on_back)
        self.finish_requested.connect(self._on_finish)
        self.cancel_requested.connect(self.reject)

    # ── Public API ────────────────────────────────────────────────

    @property
    def completed(self) -> bool:
        return self._success

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        employee: EmployeeListItemDTO,
        parent: QWidget | None = None,
    ) -> bool:
        dlg = cls(service_registry, company_id, employee, parent=parent)
        dlg.exec()
        return dlg.completed

    # ── Step builders ─────────────────────────────────────────────

    def _build_confirm_step(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        card = _card(w, "Employee to Rehire")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        for i, (label, value) in enumerate((
            ("Employee No.", self._employee.employee_number),
            ("Full Name", self._employee.display_name),
            ("Department", self._employee.department_name or "\u2014"),
            ("Position", self._employee.position_name or "\u2014"),
            ("Original Hire Date",
             str(self._employee.hire_date) if self._employee.hire_date else "\u2014"),
            ("Termination Date",
             str(self._employee.termination_date) if self._employee.termination_date else "\u2014"),
            ("Current Status", "Active" if self._employee.is_active else "Inactive"),
        )):
            key_lbl = QLabel(f"<b>{label}</b>")
            key_lbl.setObjectName("DetailKey")
            val_lbl = QLabel(value)
            val_lbl.setObjectName("DetailValue")
            grid.addWidget(key_lbl, i, 0)
            grid.addWidget(val_lbl, i, 1)

        card.layout().addLayout(grid)
        outer.addWidget(card)
        outer.addStretch(1)
        return w

    def _build_terms_step(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        card = _card(w, "Rehire Terms")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        today = date.today()
        self._hire_date_edit = QDateEdit()
        self._hire_date_edit.setCalendarPopup(True)
        self._hire_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._hire_date_edit.setDate(QDate(today.year, today.month, today.day))

        date_lbl = QLabel("New Hire Date *")
        date_lbl.setObjectName("FieldLabel")
        date_row = QHBoxLayout()
        date_row.setSpacing(6)
        date_row.addWidget(date_lbl)
        date_row.addWidget(self._hire_date_edit)
        date_row.addStretch(1)
        grid.addLayout(date_row, 0, 0, 1, 2)

        hint = QLabel(
            "The termination date will be cleared. The employee will be "
            "marked active from the new hire date.",
            w,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)

        card.layout().addLayout(grid)
        card.layout().addWidget(hint)
        outer.addWidget(card)
        outer.addStretch(1)
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

        outer.addWidget(card)
        outer.addStretch(1)
        return w

    # ── Navigation ────────────────────────────────────────────────

    def _on_next(self, step_id: str) -> None:
        if step_id == _STEP_CONFIRM:
            self.set_step_issues(_STEP_CONFIRM, [])
            self.advance_step()
        elif step_id == _STEP_TERMS:
            issues = self._validate_terms()
            if issues:
                self.set_step_issues(_STEP_TERMS, issues)
                return
            self.set_step_issues(_STEP_TERMS, [])
            self._refresh_review()
            self.advance_step()

    def _on_back(self, step_id: str) -> None:
        self.go_back()

    def _on_finish(self) -> None:
        self._apply()

    # ── Helpers ───────────────────────────────────────────────────

    def _validate_terms(self) -> list[ValidationIssue]:
        new_hire = self._hire_date_edit.date().toPython()
        original = self._employee.hire_date
        if original and new_hire < original:
            return [
                ValidationIssue(
                    severity="warning",
                    message=(
                        f"New hire date ({new_hire}) is earlier than the original hire date "
                        f"({original}). Confirm this is intentional."
                    ),
                )
            ]
        return []

    def _refresh_review(self) -> None:
        new_hire = self._hire_date_edit.date().toPython()
        self._review_label.setText(
            f"<b>Employee:</b> {self._employee.display_name} "
            f"({self._employee.employee_number})<br>"
            f"<b>New Hire Date:</b> {new_hire.isoformat()}<br>"
            f"<b>Previous Termination Date:</b> "
            f"{self._employee.termination_date or '\u2014'}<br><br>"
            "Clicking <b>Confirm Rehire</b> will mark the employee as active "
            "and update the hire date."
        )

    def _apply(self) -> None:
        new_hire = self._hire_date_edit.date().toPython()
        cmd = RehireEmployeeCommand(new_hire_date=new_hire)
        self.set_status_text("Applying rehire...")
        try:
            self._registry.employee_service.rehire_employee(
                self._company_id,
                self._employee.id,
                cmd,
            )
        except (ValidationError, NotFoundError) as exc:
            self.set_step_issues(
                _STEP_REVIEW, [ValidationIssue(severity="error", message=str(exc))]
            )
            self.set_status_text("")
            return
        except Exception as exc:  # noqa: BLE001
            _log.exception("Rehire failed")
            self.set_step_issues(
                _STEP_REVIEW,
                [ValidationIssue(severity="error", message=f"Unexpected error: {exc}")],
            )
            self.set_status_text("")
            return

        self._success = True
        self.set_status_text("Rehire applied.")
        self.accept()
