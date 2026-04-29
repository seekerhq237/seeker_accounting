"""Step 1 — Header (entry date, reference, description)."""
from __future__ import annotations

from datetime import date as _date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.opening_balances import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class HeaderStep(WizardStep):
    key = "header"
    title = "Header"
    subtitle = "Opening date and reference for the journal entry."

    def __init__(self) -> None:
        super().__init__()
        self._date: QDateEdit | None = None
        self._reference: QLineEdit | None = None
        self._description: QTextEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._date = QDateEdit(root)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setDate(QDate.currentDate())
        form.addRow(QLabel("Opening date:", root), self._date)

        self._reference = QLineEdit(root)
        self._reference.setPlaceholderText("e.g. OPENING-2026")
        form.addRow(QLabel("Reference:", root), self._reference)

        self._description = QTextEdit(root)
        self._description.setMaximumHeight(70)
        self._description.setPlaceholderText(
            "e.g. Opening balances brought forward from prior system"
        )
        form.addRow(QLabel("Description:", root), self._description)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._date is not None:
            d = state.get(K.KEY_ENTRY_DATE)
            if isinstance(d, str):
                qd = QDate.fromString(d, "yyyy-MM-dd")
                if qd.isValid():
                    self._date.setDate(qd)
        if self._reference is not None and state.get(K.KEY_REFERENCE_TEXT):
            self._reference.setText(str(state[K.KEY_REFERENCE_TEXT]))
        if self._description is not None and state.get(K.KEY_DESCRIPTION):
            self._description.setPlainText(str(state[K.KEY_DESCRIPTION]))

    def write_back(self, state: WizardState) -> None:
        if self._date is not None:
            state[K.KEY_ENTRY_DATE] = self._date.date().toString("yyyy-MM-dd")
        if self._reference is not None:
            state[K.KEY_REFERENCE_TEXT] = self._reference.text().strip() or None
        if self._description is not None:
            state[K.KEY_DESCRIPTION] = self._description.toPlainText().strip() or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        d = state.get(K.KEY_ENTRY_DATE)
        if not d:
            return StepValidationResult.fail("Opening date is required.")
        try:
            _date.fromisoformat(str(d))
        except ValueError:
            return StepValidationResult.fail("Opening date is invalid.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        d = state.get(K.KEY_ENTRY_DATE)
        return f"OPENING entry on {d}" if d else None
