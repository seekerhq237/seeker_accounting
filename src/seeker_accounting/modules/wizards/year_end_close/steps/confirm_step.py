"""Step 3 — Confirm: close the fiscal year."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.wizards.year_end_close import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Close fiscal year"
    subtitle = "Final confirmation."

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
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            self._summary.setText(
                f"<b>Fiscal year:</b> {state.get(K.KEY_FISCAL_YEAR_CODE)}<br>"
                f"<b>Periods locked at this run:</b> "
                f"{state.get(K.KEY_PERIODS_LOCKED_COUNT) or 0}<br>"
                "<br>"
                "Closing the year sets its status to CLOSED. Posting to any period in "
                "the year will then be blocked by the period control service. This "
                "action is reversible only by an administrator workflow."
            )
        if self._result is not None and state.get(K.KEY_YEAR_CLOSED):
            self._result.setText("Fiscal year closed.")

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_YEAR_CLOSED):
            return
        company_id = context.require_company_id()
        fy_id = state.get(K.KEY_FISCAL_YEAR_ID)
        if not isinstance(fy_id, int):
            return
        context.service_registry.fiscal_calendar_service.close_year(
            company_id, fy_id, actor_user_id=context.user_id
        )
        state[K.KEY_YEAR_CLOSED] = True

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        return "Closed." if state.get(K.KEY_YEAR_CLOSED) else "Ready to close."
