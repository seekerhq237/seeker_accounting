"""Step 3 — Confirm & post the reversal."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.accounting.journals.dto.journal_reversal_dto import (
    ReverseJournalCommand,
)
from seeker_accounting.modules.wizards.journal_reversal import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Create the reversing journal entry."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._result: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._summary)
        self._result = QLabel(root)
        self._result.setObjectName("WizardSuccessText")
        self._result.setWordWrap(True)
        self._result.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            auto = "Yes" if state.get(K.KEY_AUTO_POST) else "No (draft only)"
            self._summary.setText(
                f"<b>Source entry:</b> {state.get(K.KEY_SOURCE_ENTRY_NUMBER) or '?'} "
                f"({state.get(K.KEY_SOURCE_ENTRY_DATE)})<br>"
                f"<b>Source total:</b> {state.get(K.KEY_SOURCE_TOTAL)}<br>"
                f"<b>Reversal date:</b> {state.get(K.KEY_REVERSAL_DATE)}<br>"
                f"<b>Auto-post:</b> {auto}<br><br>"
                "Clicking Finish creates a balanced reversal with debits and credits "
                "swapped from the source entry."
            )
        if self._result is not None and state.get(K.KEY_POSTED):
            self._result.setText(
                f"<b>Reversal created.</b><br>"
                f"Reversal entry: {state.get(K.KEY_RESULT_REVERSAL_ENTRY_NUMBER)}<br>"
                f"Auto-posted: {'yes' if state.get(K.KEY_RESULT_AUTO_POSTED) else 'no'}"
            )

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_POSTED):
            return
        company_id = context.require_company_id()
        cmd = ReverseJournalCommand(
            reversal_date=state[K.KEY_REVERSAL_DATE],
            reason=state[K.KEY_REASON],
            auto_post=bool(state.get(K.KEY_AUTO_POST, True)),
        )
        result = context.service_registry.journal_reversal_service.reverse_journal(
            company_id,
            int(state[K.KEY_SOURCE_JE_ID]),
            cmd,
            actor_user_id=context.user_id,
        )
        state[K.KEY_RESULT_REVERSAL_JE_ID] = int(result.reversal_journal_entry_id)
        state[K.KEY_RESULT_REVERSAL_ENTRY_NUMBER] = result.reversal_entry_number
        state[K.KEY_RESULT_AUTO_POSTED] = bool(result.auto_posted)
        state[K.KEY_POSTED] = True
