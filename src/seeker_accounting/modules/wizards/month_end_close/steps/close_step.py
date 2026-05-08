"""Step 4 — Confirm and close the period."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.month_end_close import state_keys as K
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class CloseStep(WizardStep):
    key = "close"
    title = "Close Period"
    subtitle = "Review and close the selected period."

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
            "Closing changes the period status from OPEN to CLOSED. New "
            "postings will be rejected. A user with the appropriate "
            "permission can reopen the period later.",
            root,
        )
        warning.setWordWrap(True)
        warning.setObjectName("WizardWarningText")
        outer.addWidget(warning)

        self._confirm = QCheckBox("I confirm the period should be closed.", root)
        outer.addWidget(self._confirm)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._summary is not None:
            code = state.get(K.KEY_PERIOD_CODE) or "(unknown)"
            drafts = state.get(K.KEY_DRAFTS_COUNT, 0)
            gaps: list[str] = []
            if not state.get(K.KEY_RECON_BANK_ACK):
                gaps.append("bank/cash")
            if not state.get(K.KEY_RECON_AR_ACK):
                gaps.append("AR control")
            if not state.get(K.KEY_RECON_AP_ACK):
                gaps.append("AP control")
            extras = []
            if drafts:
                extras.append(f"{drafts} draft(s) will remain unposted")
            if gaps:
                extras.append("unconfirmed reconciliations: " + ", ".join(gaps))
            tail = ("\n• " + "\n• ".join(extras)) if extras else ""
            self._summary.setText(f"About to close period {code}.{tail}")
        if self._confirm is not None:
            self._confirm.setChecked(bool(state.get(K.KEY_CLOSE_CONFIRMED)))

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_CLOSE_CONFIRMED] = bool(self._confirm and self._confirm.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_CLOSE_CONFIRMED):
            return StepValidationResult.fail("Confirm the close before finishing.")
        if state.get(K.KEY_PERIOD_ID) is None:
            return StepValidationResult.fail("No period was selected.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_CLOSE_RESULT_NEW_STATUS):
            return
        company_id = context.require_company_id()
        period_id = state.get(K.KEY_PERIOD_ID)
        if not isinstance(period_id, int):
            raise ValidationError("Selected period is invalid.")
        service = context.service_registry.period_control_service
        try:
            result = service.close_period(
                company_id,
                period_id,
                actor_user_id=context.user_id,
            )
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError):
            raise
        state[K.KEY_CLOSE_RESULT_PERIOD_ID] = result.fiscal_period_id
        state[K.KEY_CLOSE_RESULT_NEW_STATUS] = result.status_code

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        code = state.get(K.KEY_PERIOD_CODE)
        new_status = state.get(K.KEY_CLOSE_RESULT_NEW_STATUS)
        if new_status:
            return f"Period {code} status: {new_status}."
        return f"Close period {code} (set status to CLOSED)."
