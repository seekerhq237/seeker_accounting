"""Step 3 — Confirm and post the FX revaluation journal entry."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.accounting.journals.dto.fx_revaluation_dto import (
    FxRevaluationCommand,
    FxRevaluationLineCommand,
)
from seeker_accounting.modules.wizards.fx_revaluation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ConfirmStep(WizardStep):
    key = "confirm"
    title = "Confirm"
    subtitle = "Review the proposed revaluation and post."

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
        rows = state.get(K.KEY_LINES) or ()
        total_gain = Decimal("0")
        total_loss = Decimal("0")
        line_html = []
        for row in rows:
            try:
                cur = Decimal(str(row.get("current_book_amount") or "0"))
                tgt = Decimal(str(row.get("target_amount") or "0"))
            except Exception:
                continue
            delta = tgt - cur
            if delta == 0:
                continue
            sign = "+" if delta > 0 else ""
            line_html.append(
                f"&nbsp;&nbsp;Account #{row.get('account_id')}: "
                f"{cur} → {tgt} ({sign}{delta})"
            )
            if delta > 0:
                total_gain += delta
            else:
                total_loss += -delta
        net = total_gain - total_loss

        if self._summary is not None:
            html = (
                f"<b>Revaluation date:</b> {state.get(K.KEY_REVALUATION_DATE)}<br>"
                f"<b>Reference:</b> {state.get(K.KEY_REFERENCE) or '(none)'}<br><br>"
                f"<b>Adjustments ({len(line_html)}):</b><br>"
                + "<br>".join(line_html)
                + "<br><br>"
                f"<b>Total gain side:</b> {total_gain}<br>"
                f"<b>Total loss side:</b> {total_loss}<br>"
                f"<b>Net:</b> {net} "
                + ("(unrealized gain)" if net > 0 else "(unrealized loss)" if net < 0 else "(net zero)")
            )
            self._summary.setText(html)
        if self._result is not None and state.get(K.KEY_POSTED):
            self._result.setText(
                f"<b>Revaluation posted.</b><br>"
                f"Journal entry: {state.get(K.KEY_RESULT_JE_NUMBER)}<br>"
                f"Total gain: {state.get(K.KEY_RESULT_GAIN)} | "
                f"Total loss: {state.get(K.KEY_RESULT_LOSS)} | "
                f"Net: {state.get(K.KEY_RESULT_NET)}"
            )

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_POSTED):
            return
        company_id = context.require_company_id()
        rows = state.get(K.KEY_LINES) or ()
        line_cmds: list[FxRevaluationLineCommand] = []
        for row in rows:
            account_id = row.get("account_id")
            if not isinstance(account_id, int):
                continue
            try:
                cur = Decimal(str(row.get("current_book_amount") or "0"))
                tgt = Decimal(str(row.get("target_amount") or "0"))
            except Exception:
                continue
            line_cmds.append(
                FxRevaluationLineCommand(
                    account_id=account_id,
                    current_book_amount=cur,
                    target_amount=tgt,
                    description=row.get("description"),
                )
            )
        cmd = FxRevaluationCommand(
            revaluation_date=state[K.KEY_REVALUATION_DATE],
            lines=tuple(line_cmds),
            gain_account_id=int(state[K.KEY_GAIN_ACCOUNT_ID]),
            loss_account_id=int(state[K.KEY_LOSS_ACCOUNT_ID]),
            reference=state.get(K.KEY_REFERENCE),
        )
        result = context.service_registry.fx_revaluation_service.post_revaluation(
            company_id, cmd, actor_user_id=context.user_id
        )
        state[K.KEY_RESULT_JE_ID] = int(result.journal_entry_id)
        state[K.KEY_RESULT_JE_NUMBER] = result.journal_entry_number
        state[K.KEY_RESULT_GAIN] = result.total_gain
        state[K.KEY_RESULT_LOSS] = result.total_loss
        state[K.KEY_RESULT_NET] = result.net_adjustment
        state[K.KEY_POSTED] = True
