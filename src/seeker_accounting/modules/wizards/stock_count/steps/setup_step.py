"""Step 1 — Setup: count date, location, adjustment account, reference."""
from __future__ import annotations

from datetime import date as date_type

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.stock_count import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class SetupStep(WizardStep):
    key = "setup"
    title = "Setup"
    subtitle = "Pick the count date, optional location, and the variance offset account."

    def __init__(self) -> None:
        super().__init__()
        self._date: QDateEdit | None = None
        self._location: QComboBox | None = None
        self._account: QComboBox | None = None
        self._reference: QLineEdit | None = None
        self._notes: QPlainTextEdit | None = None
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
        form.addRow(QLabel("Count date:", root), self._date)

        self._location = QComboBox(root)
        form.addRow(QLabel("Location (optional):", root), self._location)

        self._account = QComboBox(root)
        form.addRow(QLabel("Variance offset account:", root), self._account)

        self._reference = QLineEdit(root)
        self._reference.setMaxLength(60)
        form.addRow(QLabel("Reference:", root), self._reference)

        self._notes = QPlainTextEdit(root)
        self._notes.setFixedHeight(60)
        form.addRow(QLabel("Notes:", root), self._notes)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if not self._loaded:
            self._populate(context)
            self._loaded = True
        if self._date is not None and isinstance(state.get(K.KEY_COUNT_DATE), date_type):
            d = state[K.KEY_COUNT_DATE]
            self._date.setDate(QDate(d.year, d.month, d.day))
        if self._location is not None:
            self._select(self._location, state.get(K.KEY_LOCATION_ID))
        if self._account is not None:
            self._select(self._account, state.get(K.KEY_ADJUSTMENT_ACCOUNT_ID))
        if self._reference is not None and state.get(K.KEY_REFERENCE):
            self._reference.setText(str(state[K.KEY_REFERENCE]))
        if self._notes is not None and state.get(K.KEY_NOTES):
            self._notes.setPlainText(str(state[K.KEY_NOTES]))

    def _populate(self, context: WizardContext) -> None:
        company_id = context.require_company_id()
        if self._location is not None:
            self._location.clear()
            self._location.addItem("(any/no specific location)", None)
            try:
                locations = context.service_registry.inventory_location_service.list_inventory_locations(
                    company_id, active_only=True
                )
                for loc in locations:
                    self._location.addItem(f"{loc.code} — {loc.name}", int(loc.id))
            except Exception:
                pass
        if self._account is not None:
            self._account.clear()
            self._account.addItem("(select account)", None)
            try:
                options = context.service_registry.chart_of_accounts_service.list_account_lookup_options(
                    company_id, active_only=True
                )
                for a in options:
                    if not a.is_active or not a.allow_manual_posting:
                        continue
                    self._account.addItem(f"{a.account_code} — {a.account_name}", int(a.id))
            except Exception:
                pass

    def _select(self, combo: QComboBox, value: object) -> None:
        if not isinstance(value, int):
            combo.setCurrentIndex(0)
            return
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def write_back(self, state: WizardState) -> None:
        if self._date is not None:
            qd = self._date.date()
            state[K.KEY_COUNT_DATE] = date_type(qd.year(), qd.month(), qd.day())
        if self._location is not None:
            data = self._location.currentData()
            state[K.KEY_LOCATION_ID] = int(data) if isinstance(data, int) else None
        if self._account is not None:
            data = self._account.currentData()
            state[K.KEY_ADJUSTMENT_ACCOUNT_ID] = int(data) if isinstance(data, int) else None
        if self._reference is not None:
            state[K.KEY_REFERENCE] = self._reference.text().strip() or None
        if self._notes is not None:
            text = self._notes.toPlainText().strip()
            state[K.KEY_NOTES] = text or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_COUNT_DATE), date_type):
            return StepValidationResult.fail("Pick a count date.")
        if not isinstance(state.get(K.KEY_ADJUSTMENT_ACCOUNT_ID), int):
            return StepValidationResult.fail("Pick the variance offset account.")
        return StepValidationResult.ok()
