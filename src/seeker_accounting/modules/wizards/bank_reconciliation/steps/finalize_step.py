"""Step 3 \u2014 Finalize the reconciliation session."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.bank_reconciliation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class FinalizeStep(WizardStep):
    key = "finalize"
    title = "Finalize"
    subtitle = "Mark the session complete."

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

        warn = QLabel(
            "Once completed, the session becomes read-only and cannot accept "
            "further matches. You can resume incomplete sessions later instead.",
            root,
        )
        warn.setWordWrap(True)
        warn.setObjectName("WizardWarningText")
        outer.addWidget(warn)

        self._confirm = QCheckBox("I confirm the reconciliation is complete.", root)
        outer.addWidget(self._confirm)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            sid = state.get(K.KEY_SESSION_ID)
            m = state.get(K.KEY_MATCHED_COUNT, 0)
            u = state.get(K.KEY_UNMATCHED_COUNT, 0)
            self._summary.setText(
                f"Session #{sid}: {m} matched, {u} unmatched line(s)."
            )

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_FINALIZE_CONFIRMED] = bool(self._confirm and self._confirm.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_FINALIZE_CONFIRMED):
            return StepValidationResult.fail("Confirm to complete the session.")
        if not isinstance(state.get(K.KEY_SESSION_ID), int):
            return StepValidationResult.fail("No session to finalize.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_SESSION_STATUS) == "completed":
            return
        company_id = context.require_company_id()
        result = context.service_registry.bank_reconciliation_service.complete_session(
            company_id, int(state[K.KEY_SESSION_ID]), actor_user_id=context.user_id
        )
        state[K.KEY_SESSION_STATUS] = result.status_code

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        if state.get(K.KEY_SESSION_STATUS) == "completed":
            return f"Session #{state.get(K.KEY_SESSION_ID)} completed."
        return f"Finalize session #{state.get(K.KEY_SESSION_ID)}."
