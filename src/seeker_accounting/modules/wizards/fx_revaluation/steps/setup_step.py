"""Step 1 — Setup: revaluation date, gain account, loss account, reference."""
from __future__ import annotations

from datetime import date as date_type

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.fx_revaluation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class SetupStep(WizardStep):
    key = "setup"
    title = "Setup"
    subtitle = "Pick the revaluation date and the gain/loss accounts."

    def __init__(self) -> None:
        super().__init__()
        self._date: QDateEdit | None = None
        self._gain: QComboBox | None = None
        self._loss: QComboBox | None = None
        self._reference: QLineEdit | None = None
        self._loaded = False

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
        form.addRow(QLabel("Revaluation date:", root), self._date)

        self._gain = QComboBox(root)
        form.addRow(QLabel("Unrealized gain account (CR):", root), self._gain)

        self._loss = QComboBox(root)
        form.addRow(QLabel("Unrealized loss account (DR):", root), self._loss)

        self._reference = QLineEdit(root)
        self._reference.setMaxLength(120)
        form.addRow(QLabel("Reference:", root), self._reference)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if not self._loaded:
            self._populate_accounts(context)
            self._loaded = True
        if self._date is not None and isinstance(state.get(K.KEY_REVALUATION_DATE), date_type):
            d = state[K.KEY_REVALUATION_DATE]
            self._date.setDate(QDate(d.year, d.month, d.day))
        if self._gain is not None:
            self._select(self._gain, state.get(K.KEY_GAIN_ACCOUNT_ID))
        if self._loss is not None:
            self._select(self._loss, state.get(K.KEY_LOSS_ACCOUNT_ID))
        if self._reference is not None and state.get(K.KEY_REFERENCE):
            self._reference.setText(str(state[K.KEY_REFERENCE]))

    def _populate_accounts(self, context: WizardContext) -> None:
        if self._gain is None or self._loss is None:
            return
        company_id = context.require_company_id()
        try:
            options = context.service_registry.chart_of_accounts_service.list_account_lookup_options(
                company_id, active_only=True
            )
        except Exception:
            options = []
        for combo in (self._gain, self._loss):
            combo.clear()
            combo.addItem("(select account)", None)
            for a in options:
                if not a.is_active or not a.allow_manual_posting:
                    continue
                combo.addItem(f"{a.account_code} — {a.account_name}", int(a.id))

    def _select(self, combo: QComboBox, value: object) -> None:
        if not isinstance(value, int):
            combo.setCurrentIndex(0)
            return
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def write_back(self, state: WizardState) -> None:
        if self._date is not None:
            qd = self._date.date()
            state[K.KEY_REVALUATION_DATE] = date_type(qd.year(), qd.month(), qd.day())
        if self._gain is not None:
            data = self._gain.currentData()
            state[K.KEY_GAIN_ACCOUNT_ID] = int(data) if isinstance(data, int) else None
        if self._loss is not None:
            data = self._loss.currentData()
            state[K.KEY_LOSS_ACCOUNT_ID] = int(data) if isinstance(data, int) else None
        if self._reference is not None:
            state[K.KEY_REFERENCE] = self._reference.text().strip() or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_REVALUATION_DATE), date_type):
            return StepValidationResult.fail("Pick a revaluation date.")
        if not isinstance(state.get(K.KEY_GAIN_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick the unrealized gain account.")
        if not isinstance(state.get(K.KEY_LOSS_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick the unrealized loss account.")
        if state[K.KEY_GAIN_ACCOUNT_ID] == state[K.KEY_LOSS_ACCOUNT_ID]:
            return StepValidationResult.fail(
                "Gain and loss accounts must be different."
            )
        return StepValidationResult.ok()
