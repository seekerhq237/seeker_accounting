"""Step 2 — Capture a written reason and explicit acknowledgement."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QTextEdit,
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


_MIN_REASON_LENGTH = 10


class ReasonStep(WizardStep):
    key = "reason"
    title = "Reason"
    subtitle = "Document why this period must be reopened."

    def __init__(self) -> None:
        super().__init__()
        self._reason: QTextEdit | None = None
        self._ack: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        prompt = QLabel(
            "Reopening a closed period is auditable. Write a clear explanation "
            "(at least 10 characters) so reviewers can understand what changed.",
            root,
        )
        prompt.setWordWrap(True)
        prompt.setObjectName("WizardMutedText")
        outer.addWidget(prompt)

        self._reason = QTextEdit(root)
        self._reason.setPlaceholderText(
            "e.g. \u201cMissing invoice INV-2026-0142 from supplier ACME identified during "
            "audit; needs to be booked into period 2026-03 then re-closed.\u201d"
        )
        self._reason.setMaximumHeight(120)
        outer.addWidget(self._reason, 1)

        self._ack = QCheckBox(
            "I understand reopening allows posting into this period and is logged in the audit trail.",
            root,
        )
        outer.addWidget(self._ack)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._reason is not None and state.get(K.KEY_REASON):
            self._reason.setPlainText(str(state.get(K.KEY_REASON)))
        if self._ack is not None:
            self._ack.setChecked(bool(state.get(K.KEY_REASON_ACKNOWLEDGED)))

    def write_back(self, state: WizardState) -> None:
        if self._reason is not None:
            state[K.KEY_REASON] = self._reason.toPlainText().strip()
        if self._ack is not None:
            state[K.KEY_REASON_ACKNOWLEDGED] = bool(self._ack.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        reason = state.get(K.KEY_REASON) or ""
        if len(reason.strip()) < _MIN_REASON_LENGTH:
            return StepValidationResult.fail(
                f"Reason must be at least {_MIN_REASON_LENGTH} characters."
            )
        if not state.get(K.KEY_REASON_ACKNOWLEDGED):
            return StepValidationResult.fail("Acknowledge the reopen consequences.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        reason = state.get(K.KEY_REASON)
        if reason:
            short = reason if len(reason) <= 80 else reason[:77] + "..."
            return f"Reason: {short}"
        return None
