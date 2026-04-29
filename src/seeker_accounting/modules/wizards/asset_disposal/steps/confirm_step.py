"""Step 3 — Confirm and post the disposal journal entry."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.fixed_assets.dto.asset_disposal_dto import (
    DisposeAssetCommand,
)
from seeker_accounting.modules.wizards.asset_disposal import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm disposal"
    subtitle = "Review and post the disposal journal entry."

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
        self._result.setStyleSheet("color: #2a7;")
        self._result.setWordWrap(True)
        self._result.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._result)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            self._summary.setText(
                f"<b>Asset:</b> {state.get(K.KEY_ASSET_NUMBER)} — {state.get(K.KEY_ASSET_NAME)}<br>"
                f"<b>Disposal date:</b> {state.get(K.KEY_DISPOSAL_DATE)}<br>"
                f"<b>Proceeds:</b> {state.get(K.KEY_DISPOSAL_AMOUNT)}<br>"
                f"<b>Acquisition cost:</b> {state.get(K.KEY_ASSET_ACQUISITION_COST)}<br>"
                "<br>"
                "<i>Net book value, accumulated depreciation, and final gain/loss are "
                "computed at posting from the asset's posted depreciation history.</i>"
            )
        if self._result is not None and state.get(K.KEY_DISPOSED):
            self._result.setText(
                f"<b>Disposal posted.</b><br>"
                f"Journal entry: {state.get(K.KEY_DISPOSAL_RESULT_JE_NUMBER)}<br>"
                f"Accumulated depreciation: {state.get(K.KEY_DISPOSAL_RESULT_ACCUMULATED)}<br>"
                f"Net book value: {state.get(K.KEY_DISPOSAL_RESULT_NBV)}<br>"
                f"Gain (+) / Loss (−): {state.get(K.KEY_DISPOSAL_RESULT_GAIN_LOSS)}"
            )

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_DISPOSED):
            return
        company_id = context.require_company_id()
        asset_id = state.get(K.KEY_ASSET_ID)
        if not isinstance(asset_id, int):
            return
        cmd = DisposeAssetCommand(
            disposal_date=state[K.KEY_DISPOSAL_DATE],
            disposal_amount=Decimal(str(state.get(K.KEY_DISPOSAL_AMOUNT) or "0")),
            proceeds_account_id=int(state[K.KEY_PROCEEDS_ACCOUNT_ID]),
            gain_or_loss_account_id=int(state[K.KEY_GAIN_LOSS_ACCOUNT_ID]),
            reference=state.get(K.KEY_REFERENCE),
            notes=state.get(K.KEY_NOTES),
        )
        result = context.service_registry.asset_disposal_service.dispose_asset(
            company_id, asset_id, cmd, actor_user_id=context.user_id
        )
        state[K.KEY_DISPOSAL_RESULT_JE_ID] = int(result.journal_entry_id)
        state[K.KEY_DISPOSAL_RESULT_JE_NUMBER] = result.journal_entry_number
        state[K.KEY_DISPOSAL_RESULT_ACCUMULATED] = result.accumulated_depreciation
        state[K.KEY_DISPOSAL_RESULT_NBV] = result.net_book_value
        state[K.KEY_DISPOSAL_RESULT_GAIN_LOSS] = result.gain_or_loss_amount
        state[K.KEY_DISPOSED] = True

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        return "Posted." if state.get(K.KEY_DISPOSED) else "Ready to post."
