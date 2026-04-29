"""Step 2 — Reversal details: date, reason, auto-post."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QPlainTextEdit,
    QWidget,
)

from seeker_accounting.modules.wizards.journal_reversal import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class DetailsStep(WizardStep):
    key = "details"
    title = "Reversal details"
    subtitle = "Choose the reversal date, give a reason, and pick auto-post."

    def __init__(self) -> None:
        super().__init__()
        self._date_edit: QDateEdit | None = None
        self._reason_edit: QPlainTextEdit | None = None
        self._auto_post: QCheckBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        form = QFormLayout(root)
        form.setContentsMargins(0, 0, 0, 0)

        self._date_edit = QDateEdit(root)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDate(QDate.currentDate())
        form.addRow("Reversal date", self._date_edit)

        self._reason_edit = QPlainTextEdit(root)
        self._reason_edit.setPlaceholderText("Why is this entry being reversed?")
        self._reason_edit.setFixedHeight(96)
        form.addRow("Reason", self._reason_edit)

        self._auto_post = QCheckBox("Post the reversal immediately", root)
        self._auto_post.setChecked(True)
        form.addRow("", self._auto_post)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._date_edit is not None:
            existing = state.get(K.KEY_REVERSAL_DATE)
            if isinstance(existing, date):
                self._date_edit.setDate(QDate(existing.year, existing.month, existing.day))
        if self._reason_edit is not None:
            existing_reason = state.get(K.KEY_REASON)
            if isinstance(existing_reason, str):
                self._reason_edit.setPlainText(existing_reason)
        if self._auto_post is not None:
            existing_auto = state.get(K.KEY_AUTO_POST)
            if isinstance(existing_auto, bool):
                self._auto_post.setChecked(existing_auto)

    def write_back(self, state: WizardState) -> None:
        if self._date_edit is not None:
            qd = self._date_edit.date()
            state[K.KEY_REVERSAL_DATE] = date(qd.year(), qd.month(), qd.day())
        if self._reason_edit is not None:
            state[K.KEY_REASON] = self._reason_edit.toPlainText().strip()
        if self._auto_post is not None:
            state[K.KEY_AUTO_POST] = self._auto_post.isChecked()

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_REVERSAL_DATE), date):
            return StepValidationResult.fail("Pick a reversal date.")
        reason = (state.get(K.KEY_REASON) or "").strip()
        if not reason:
            return StepValidationResult.fail("A reason is required for any reversal.")
        return StepValidationResult.ok()
