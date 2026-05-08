"""Step 3 — Reconciliation reminders (informational).

Surfaces the standard pre-close checklist: bank/cash recs, AR control vs
subledger, AP control vs subledger. The user explicitly acknowledges each;
the wizard does not run the reconciliations itself in this slice.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.month_end_close import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ReconciliationCheckStep(WizardStep):
    key = "reconciliation_check"
    title = "Reconciliations"
    subtitle = "Confirm key reconciliations are up to date."

    def __init__(self) -> None:
        super().__init__()
        self._cb_bank: QCheckBox | None = None
        self._cb_ar: QCheckBox | None = None
        self._cb_ap: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        intro = QLabel(
            "Closing the period assumes the following reconciliations have "
            "been performed. Confirm each item; you can still close with "
            "items unchecked, but the wizard will record the gap.",
            root,
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardMutedText")
        outer.addWidget(intro)

        self._cb_bank = QCheckBox("Bank and cash accounts reconciled to statements.", root)
        self._cb_ar = QCheckBox("AR control account agrees with the customer subledger.", root)
        self._cb_ap = QCheckBox("AP control account agrees with the supplier subledger.", root)
        outer.addWidget(self._cb_bank)
        outer.addWidget(self._cb_ar)
        outer.addWidget(self._cb_ap)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._cb_bank is not None:
            self._cb_bank.setChecked(bool(state.get(K.KEY_RECON_BANK_ACK)))
        if self._cb_ar is not None:
            self._cb_ar.setChecked(bool(state.get(K.KEY_RECON_AR_ACK)))
        if self._cb_ap is not None:
            self._cb_ap.setChecked(bool(state.get(K.KEY_RECON_AP_ACK)))

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_RECON_BANK_ACK] = bool(self._cb_bank and self._cb_bank.isChecked())
        state[K.KEY_RECON_AR_ACK] = bool(self._cb_ar and self._cb_ar.isChecked())
        state[K.KEY_RECON_AP_ACK] = bool(self._cb_ap and self._cb_ap.isChecked())

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        gaps: list[str] = []
        if not state.get(K.KEY_RECON_BANK_ACK):
            gaps.append("bank/cash")
        if not state.get(K.KEY_RECON_AR_ACK):
            gaps.append("AR control")
        if not state.get(K.KEY_RECON_AP_ACK):
            gaps.append("AP control")
        if not gaps:
            return "All reconciliations confirmed."
        return f"Reconciliation gaps acknowledged: {', '.join(gaps)}."
