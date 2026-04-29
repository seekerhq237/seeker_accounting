"""Step 3 — Reopen the selected period via the period control service."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.period_reopen import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ReopenStep(WizardStep):
    key = "reopen"
    title = "Reopen"
    subtitle = "Apply the reopen and record the audit event."

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
        self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")
        outer.addWidget(self._summary)

        self._confirm = QCheckBox("I confirm this period should be reopened now.", root)
        outer.addWidget(self._confirm)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            code = state.get(K.KEY_PERIOD_CODE) or "(unknown)"
            prev = state.get(K.KEY_PREVIOUS_STATUS) or "?"
            self._summary.setText(
                f"Period {code} will move from {prev} to OPEN. "
                "The reason you entered will be persisted on the audit trail."
            )

    def write_back(self, state: WizardState) -> None:
        # No state to capture beyond confirm.
        pass

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not (self._confirm and self._confirm.isChecked()):
            return StepValidationResult.fail("Confirm to reopen.")
        if not isinstance(state.get(K.KEY_PERIOD_ID), int):
            return StepValidationResult.fail("No period selected.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_REOPEN_RESULT_NEW_STATUS):
            return
        company_id = context.require_company_id()
        period_id = int(state[K.KEY_PERIOD_ID])
        result = context.service_registry.period_control_service.reopen_period(
            company_id,
            period_id,
            actor_user_id=context.user_id,
        )
        state[K.KEY_REOPEN_RESULT_PERIOD_ID] = result.fiscal_period_id
        state[K.KEY_REOPEN_RESULT_NEW_STATUS] = result.status_code

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        if state.get(K.KEY_REOPEN_RESULT_NEW_STATUS):
            return f"Period {state.get(K.KEY_PERIOD_CODE)} is now {state.get(K.KEY_REOPEN_RESULT_NEW_STATUS)}."
        return f"Reopen {state.get(K.KEY_PERIOD_CODE)}."
