"""Step 3 — Approve the calculated payroll run."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.payroll_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ApproveStep(WizardStep):
    key = "approve"
    title = "Approve"
    subtitle = "Approve the run to freeze it for posting."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._confirm: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._summary = QLabel("", root)
        self._summary.setWordWrap(True)
        self._summary.setObjectName("WizardBodyText")
        outer.addWidget(self._summary)

        warning = QLabel(
            "Approval freezes the employee scope and prevents recalculation. "
            "After approval, only posting (or void) is available.",
            root,
        )
        warning.setWordWrap(True)
        warning.setObjectName("WizardWarningText")
        outer.addWidget(warning)

        self._confirm = QCheckBox("I confirm the run is correct and approve it.", root)
        outer.addWidget(self._confirm)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            ref = state.get(K.KEY_RUN_REFERENCE) or "(unknown)"
            n = state.get(K.KEY_EMPLOYEE_COUNT, 0)
            net = state.get(K.KEY_TOTAL_NET) or "0"
            cur = state.get(K.KEY_CURRENCY_CODE) or ""
            self._summary.setText(
                f"Run {ref} — {n} employee(s), total net {net} {cur}."
            )
        if self._confirm is not None:
            self._confirm.setChecked(bool(state.get(K.KEY_APPROVE_CONFIRMED)))

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_APPROVE_CONFIRMED] = bool(self._confirm and self._confirm.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_APPROVE_CONFIRMED):
            return StepValidationResult.fail("Confirm to approve the run.")
        if not isinstance(state.get(K.KEY_RUN_ID), int):
            return StepValidationResult.fail("No run to approve.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_RUN_STATUS) == "approved":
            return
        company_id = context.require_company_id()
        service = context.service_registry.payroll_run_service
        run_id = int(state[K.KEY_RUN_ID])
        service.approve_run(company_id, run_id)
        # Refresh status from the server side.
        run = service.get_run(company_id, run_id)
        state[K.KEY_RUN_STATUS] = run.status_code

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        if state.get(K.KEY_RUN_STATUS) == "approved":
            return f"Run {state.get(K.KEY_RUN_REFERENCE)} approved."
        return f"Approve run {state.get(K.KEY_RUN_REFERENCE)}."
