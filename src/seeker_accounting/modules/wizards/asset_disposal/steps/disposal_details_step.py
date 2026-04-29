"""Step 2 — Disposal details: date, proceeds, accounts, reference."""
from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.asset_disposal import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class DisposalDetailsStep(WizardStep):
    key = "disposal_details"
    title = "Disposal details"
    subtitle = "Capture date, proceeds, and the accounts that will be debited/credited."

    def __init__(self) -> None:
        super().__init__()
        self._date: QDateEdit | None = None
        self._amount: QDoubleSpinBox | None = None
        self._proceeds: QComboBox | None = None
        self._gain_loss: QComboBox | None = None
        self._reference: QLineEdit | None = None
        self._notes: QPlainTextEdit | None = None
        self._accounts_loaded = False

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
        form.addRow(QLabel("Disposal date:", root), self._date)

        self._amount = QDoubleSpinBox(root)
        self._amount.setRange(0.0, 999_999_999_999.0)
        self._amount.setDecimals(2)
        self._amount.setSingleStep(1000.0)
        form.addRow(QLabel("Proceeds (cash received):", root), self._amount)

        self._proceeds = QComboBox(root)
        form.addRow(QLabel("Proceeds account (DR):", root), self._proceeds)

        self._gain_loss = QComboBox(root)
        form.addRow(QLabel("Gain/Loss account:", root), self._gain_loss)

        self._reference = QLineEdit(root)
        self._reference.setMaxLength(120)
        form.addRow(QLabel("Reference:", root), self._reference)

        self._notes = QPlainTextEdit(root)
        self._notes.setFixedHeight(70)
        form.addRow(QLabel("Notes:", root), self._notes)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if not self._accounts_loaded:
            self._populate_accounts(context)
            self._accounts_loaded = True
        if self._date is not None and isinstance(state.get(K.KEY_DISPOSAL_DATE), date_type):
            d = state[K.KEY_DISPOSAL_DATE]
            self._date.setDate(QDate(d.year, d.month, d.day))
        if self._amount is not None:
            value = state.get(K.KEY_DISPOSAL_AMOUNT)
            if value is not None:
                try:
                    self._amount.setValue(float(value))
                except (TypeError, ValueError):
                    pass
        if self._proceeds is not None:
            self._select_account(self._proceeds, state.get(K.KEY_PROCEEDS_ACCOUNT_ID))
        if self._gain_loss is not None:
            self._select_account(self._gain_loss, state.get(K.KEY_GAIN_LOSS_ACCOUNT_ID))
        if self._reference is not None and state.get(K.KEY_REFERENCE):
            self._reference.setText(str(state[K.KEY_REFERENCE]))
        if self._notes is not None and state.get(K.KEY_NOTES):
            self._notes.setPlainText(str(state[K.KEY_NOTES]))

    def _populate_accounts(self, context: WizardContext) -> None:
        if self._proceeds is None or self._gain_loss is None:
            return
        company_id = context.require_company_id()
        try:
            options = context.service_registry.chart_of_accounts_service.list_account_lookup_options(
                company_id, active_only=True
            )
        except Exception:
            options = []
        for combo in (self._proceeds, self._gain_loss):
            combo.clear()
            combo.addItem("(select account)", None)
            for a in options:
                if not a.is_active or not a.allow_manual_posting:
                    continue
                combo.addItem(f"{a.account_code} — {a.account_name}", int(a.id))

    def _select_account(self, combo: QComboBox, value: object) -> None:
        if not isinstance(value, int):
            combo.setCurrentIndex(0)
            return
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def write_back(self, state: WizardState) -> None:
        if self._date is not None:
            qd = self._date.date()
            state[K.KEY_DISPOSAL_DATE] = date_type(qd.year(), qd.month(), qd.day())
        if self._amount is not None:
            state[K.KEY_DISPOSAL_AMOUNT] = Decimal(str(self._amount.value()))
        if self._proceeds is not None:
            data = self._proceeds.currentData()
            state[K.KEY_PROCEEDS_ACCOUNT_ID] = int(data) if isinstance(data, int) else None
        if self._gain_loss is not None:
            data = self._gain_loss.currentData()
            state[K.KEY_GAIN_LOSS_ACCOUNT_ID] = int(data) if isinstance(data, int) else None
        if self._reference is not None:
            state[K.KEY_REFERENCE] = self._reference.text().strip() or None
        if self._notes is not None:
            text = self._notes.toPlainText().strip()
            state[K.KEY_NOTES] = text or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_DISPOSAL_DATE), date_type):
            return StepValidationResult.fail("Pick a disposal date.")
        if not isinstance(state.get(K.KEY_PROCEEDS_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick the proceeds account.")
        if not isinstance(state.get(K.KEY_GAIN_LOSS_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick the gain/loss account.")
        if state.get(K.KEY_PROCEEDS_ACCOUNT_ID) == state.get(K.KEY_GAIN_LOSS_ACCOUNT_ID):
            return StepValidationResult.fail(
                "Proceeds and gain/loss accounts must be different."
            )
        return StepValidationResult.ok()
