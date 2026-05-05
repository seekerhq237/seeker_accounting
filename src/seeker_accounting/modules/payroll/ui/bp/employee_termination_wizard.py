"""TerminateEmployeeWizardDialog — P4.S6 Termination Business Process.

3-step WizardShell workflow:

1. **Confirm** — shows employee details, effective termination date.
2. **Details**  — captures reason and optional last pay date.
3. **Review**   — summary + final confirmation before the service call.
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
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.employee_dto import (
    EmployeeListItemDTO,
    TerminateEmployeeCommand,
)
from seeker_accounting.platform.exceptions import (
    NotFoundError,
    ValidationError,
)
from seeker_accounting.shared.ui.components.wizard_shell import (
    ValidationIssue,
    WizardShell,
    WizardStepDescriptor,
)

_log = logging.getLogger(__name__)

_STEP_CONFIRM = "confirm"
_STEP_DETAILS = "details"
_STEP_REVIEW = "review"

_STEPS: Sequence[WizardStepDescriptor] = (
    WizardStepDescriptor(id=_STEP_CONFIRM, title="Confirm Employee",
                         description="Verify you are terminating the correct employee."),
    WizardStepDescriptor(id=_STEP_DETAILS, title="Termination Details",
                         description="Effective date, reason, and optional last pay date."),
    WizardStepDescriptor(id=_STEP_REVIEW, title="Review & Apply",
                         description="Summary before finalising the termination."),
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


class TerminateEmployeeWizardDialog(WizardShell):
    """Guided 3-step termination wizard."""

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
            f"Terminate Employee \u2014 {employee.display_name}",
            _STEPS,
            parent=parent,
            finish_label="Confirm Termination",
            min_width=660,
            min_height=520,
        )
        self.setObjectName("TerminateEmployeeWizardDialog")

        self.set_step_widget(_STEP_CONFIRM, self._build_confirm_step())
        self.set_step_widget(_STEP_DETAILS, self._build_details_step())
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

        card = _card(w, "Employee to Terminate")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        for i, (label, value) in enumerate((
            ("Employee No.", self._employee.employee_number),
            ("Full Name", self._employee.display_name),
            ("Department", self._employee.department_name or "\u2014"),
            ("Position", self._employee.position_name or "\u2014"),
            ("Original Hire Date", str(self._employee.hire_date) if self._employee.hire_date else "\u2014"),
            ("Status", "Active" if self._employee.is_active else "Inactive"),
        )):
            key_lbl = QLabel(f"<b>{label}</b>")
            key_lbl.setObjectName("DetailKey")
            val_lbl = QLabel(value)
            val_lbl.setObjectName("DetailValue")
            grid.addWidget(key_lbl, i, 0)
            grid.addWidget(val_lbl, i, 1)

        card.layout().addLayout(grid)

        warn = QLabel(
            "\u26a0\ufe0f  Terminating an employee sets them inactive and records a "
            "termination date. Any payroll runs still in draft or approved state "
            "that include this employee should be reviewed before applying.",
            w,
        )
        warn.setObjectName("DialogWarningLabel")
        warn.setWordWrap(True)

        outer.addWidget(card)
        outer.addWidget(warn)
        outer.addStretch(1)
        return w

    def _build_details_step(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        card = _card(w, "Termination Details")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        today = date.today()
        self._term_date_edit = QDateEdit()
        self._term_date_edit.setCalendarPopup(True)
        self._term_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._term_date_edit.setDate(QDate(today.year, today.month, today.day))

        date_lbl = QLabel("Effective Date *")
        date_lbl.setObjectName("FieldLabel")
        date_row = QHBoxLayout()
        date_row.setSpacing(6)
        date_row.addWidget(date_lbl)
        date_row.addWidget(self._term_date_edit)
        date_row.addStretch(1)
        grid.addLayout(date_row, 0, 0, 1, 2)

        self._last_pay_edit = QDateEdit()
        self._last_pay_edit.setCalendarPopup(True)
        self._last_pay_edit.setDisplayFormat("yyyy-MM-dd")
        self._last_pay_edit.setDate(QDate(today.year, today.month, today.day))
        self._last_pay_edit.setSpecialValueText("\u2014 Not set \u2014")

        lp_lbl = QLabel("Last Pay Date")
        lp_lbl.setObjectName("FieldLabel")
        lp_row = QHBoxLayout()
        lp_row.setSpacing(6)
        lp_row.addWidget(lp_lbl)
        lp_row.addWidget(self._last_pay_edit)
        lp_row.addStretch(1)
        grid.addLayout(lp_row, 1, 0, 1, 2)

        self._reason_edit = QLineEdit()
        self._reason_edit.setPlaceholderText(
            "Required \u2014 e.g. Resignation, Redundancy, End of contract"
        )
        self._reason_edit.setMaxLength(255)
        reason_lbl = QLabel("Reason *")
        reason_lbl.setObjectName("FieldLabel")
        grid.addWidget(reason_lbl, 2, 0)
        grid.addWidget(self._reason_edit, 2, 1)

        card.layout().addLayout(grid)
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

        elif step_id == _STEP_DETAILS:
            issues = self._validate_details()
            if issues:
                self.set_step_issues(_STEP_DETAILS, issues)
                return
            self.set_step_issues(_STEP_DETAILS, [])
            self._refresh_review()
            self.advance_step()

    def _on_back(self, step_id: str) -> None:
        self.go_back()

    def _on_finish(self) -> None:
        self._apply()

    # ── Helpers ───────────────────────────────────────────────────

    def _validate_details(self) -> list[ValidationIssue]:
        reason = self._reason_edit.text().strip()
        if not reason:
            return [ValidationIssue(severity="error", message="Reason is required.")]
        return []

    def _refresh_review(self) -> None:
        term_date = self._term_date_edit.date().toPython()
        reason = self._reason_edit.text().strip()
        self._review_label.setText(
            f"<b>Employee:</b> {self._employee.display_name} "
            f"({self._employee.employee_number})<br>"
            f"<b>Effective Termination Date:</b> {term_date.isoformat()}<br>"
            f"<b>Reason:</b> {reason or '\u2014'}<br><br>"
            "Clicking <b>Confirm Termination</b> will mark the employee as "
            "inactive. This can be reversed via the Rehire wizard."
        )

    def _apply(self) -> None:
        term_date = self._term_date_edit.date().toPython()
        reason = self._reason_edit.text().strip()
        cmd = TerminateEmployeeCommand(
            termination_date=term_date,
            reason=reason,
        )
        self.set_status_text("Applying termination...")
        try:
            self._registry.employee_service.terminate_employee(
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
            _log.exception("Termination failed")
            self.set_step_issues(
                _STEP_REVIEW,
                [ValidationIssue(severity="error", message=f"Unexpected error: {exc}")],
            )
            self.set_status_text("")
            return

        self._success = True
        self.set_status_text("Termination applied.")
        self.accept()
