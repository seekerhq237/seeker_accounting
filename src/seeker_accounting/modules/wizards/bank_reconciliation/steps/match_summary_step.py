"""Step 2 \u2014 Show the matching summary so the user can decide whether to finalize."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
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


class MatchSummaryStep(WizardStep):
    key = "match_summary"
    title = "Matching"
    subtitle = "Review match progress for this session."

    def __init__(self) -> None:
        super().__init__()
        self._matched: QLabel | None = None
        self._unmatched: QLabel | None = None
        self._total: QLabel | None = None
        self._tip: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._tip = QLabel(
            "Use the Bank Reconciliation page to record matches between "
            "statement lines and the corresponding system documents. Refresh "
            "this step to see updated counts.",
            root,
        )
        self._tip.setWordWrap(True)
        self._tip.setObjectName("WizardMutedText")
        outer.addWidget(self._tip)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self._matched = QLabel("0", root)
        self._unmatched = QLabel("0", root)
        self._total = QLabel("0.00", root)
        for w in (self._matched, self._unmatched, self._total):
            w.setObjectName("WizardBodyTextStrong")
        form.addRow(QLabel("Matched lines:", root), self._matched)
        form.addRow(QLabel("Unmatched lines:", root), self._unmatched)
        form.addRow(QLabel("Total matched amount:", root), self._total)
        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        session_id = state.get(K.KEY_SESSION_ID)
        if not isinstance(session_id, int):
            return
        company_id = context.require_company_id()
        summary = context.service_registry.bank_reconciliation_service.get_reconciliation_summary(
            company_id, session_id
        )
        state[K.KEY_MATCHED_COUNT] = summary.matched_statement_count
        state[K.KEY_UNMATCHED_COUNT] = summary.unmatched_statement_count
        state[K.KEY_TOTAL_MATCHED] = str(summary.total_matched_amount)
        if self._matched is not None:
            self._matched.setText(str(summary.matched_statement_count))
        if self._unmatched is not None:
            self._unmatched.setText(str(summary.unmatched_statement_count))
        if self._total is not None:
            self._total.setText(f"{summary.total_matched_amount:,.2f}")

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_SESSION_ID), int):
            return StepValidationResult.fail("No session loaded.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        m = state.get(K.KEY_MATCHED_COUNT, 0)
        u = state.get(K.KEY_UNMATCHED_COUNT, 0)
        return f"{m} matched / {u} unmatched line(s)."
