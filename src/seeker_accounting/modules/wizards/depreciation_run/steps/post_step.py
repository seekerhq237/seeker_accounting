"""Step 3 — Post the depreciation run to the GL."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.depreciation_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class PostStep(WizardStep):
    key = "post"
    title = "Post"
    subtitle = "Post the depreciation run to the General Ledger."

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

        self._confirm = QCheckBox("I confirm the run should be posted now.", root)
        outer.addWidget(self._confirm)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            n = state.get(K.KEY_ASSET_COUNT, 0)
            total = state.get(K.KEY_TOTAL_DEPRECIATION) or "0"
            self._summary.setText(
                f"Posting will create one balanced journal entry charging "
                f"depreciation expense and crediting accumulated depreciation "
                f"for {n} asset(s) (total {total})."
            )
        if self._confirm is not None:
            self._confirm.setChecked(bool(state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)))

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_POST_CONFIRMED] = bool(self._confirm and self._confirm.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_POST_CONFIRMED):
            return StepValidationResult.fail("Confirm to post the run.")
        if not isinstance(state.get(K.KEY_RUN_ID), int):
            return StepValidationResult.fail("No run to post.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID):
            return
        company_id = context.require_company_id()
        run_id = int(state[K.KEY_RUN_ID])
        result = context.service_registry.depreciation_posting_service.post_run(
            company_id, run_id, actor_user_id=context.user_id
        )
        state[K.KEY_POSTED_JOURNAL_ENTRY_ID] = result.posted_journal_entry_id
        state[K.KEY_RUN_NUMBER] = result.run_number
        state[K.KEY_RUN_STATUS] = "posted"
        state[K.KEY_ASSET_COUNT] = result.asset_count
        state[K.KEY_TOTAL_DEPRECIATION] = str(result.total_depreciation)

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        je = state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)
        if je:
            return f"Posted to GL \u2014 journal entry id {je}."
        return f"Post run {state.get(K.KEY_RUN_NUMBER) or '(draft)'}."
