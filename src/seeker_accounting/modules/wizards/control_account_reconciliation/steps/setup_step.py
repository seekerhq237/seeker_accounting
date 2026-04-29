"""Step 1 — Setup: pick as-of date and scope."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.control_account_reconciliation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class SetupStep(WizardStep):
    key = "setup"
    title = "Reconciliation setup"
    subtitle = "Choose the as-of date and which control accounts to reconcile."

    def __init__(self) -> None:
        super().__init__()
        self._date_edit: QDateEdit | None = None
        self._ar_check: QCheckBox | None = None
        self._ap_check: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self._date_edit = QDateEdit(root)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDate(QDate.currentDate())
        form.addRow("As-of date", self._date_edit)
        outer.addLayout(form)

        self._ar_check = QCheckBox("Reconcile AR control account vs customer subledger", root)
        self._ar_check.setChecked(True)
        outer.addWidget(self._ar_check)

        self._ap_check = QCheckBox("Reconcile AP control account vs supplier subledger", root)
        self._ap_check.setChecked(True)
        outer.addWidget(self._ap_check)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._date_edit is not None:
            existing = state.get(K.KEY_AS_OF_DATE)
            if isinstance(existing, date):
                self._date_edit.setDate(QDate(existing.year, existing.month, existing.day))
        if self._ar_check is not None:
            existing_ar = state.get(K.KEY_INCLUDE_AR)
            if isinstance(existing_ar, bool):
                self._ar_check.setChecked(existing_ar)
        if self._ap_check is not None:
            existing_ap = state.get(K.KEY_INCLUDE_AP)
            if isinstance(existing_ap, bool):
                self._ap_check.setChecked(existing_ap)

    def write_back(self, state: WizardState) -> None:
        if self._date_edit is not None:
            qd = self._date_edit.date()
            state[K.KEY_AS_OF_DATE] = date(qd.year(), qd.month(), qd.day())
        if self._ar_check is not None:
            state[K.KEY_INCLUDE_AR] = self._ar_check.isChecked()
        if self._ap_check is not None:
            state[K.KEY_INCLUDE_AP] = self._ap_check.isChecked()
        # Invalidate any prior report so the next step re-fetches.
        state[K.KEY_REPORT] = None
        state[K.KEY_REVIEWED] = False

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_AS_OF_DATE), date):
            return StepValidationResult.fail("Pick an as-of date.")
        if not (state.get(K.KEY_INCLUDE_AR) or state.get(K.KEY_INCLUDE_AP)):
            return StepValidationResult.fail(
                "Select at least one control account to reconcile."
            )
        return StepValidationResult.ok()
