"""Step 1 — Setup: as-of date, bucket unit/count, AR/AP scope."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.cash_flow_forecast_dto import (
    CashFlowBucketUnit,
)
from seeker_accounting.modules.wizards.cash_flow_forecast import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)

_UNIT_LABELS = (
    ("Weekly", CashFlowBucketUnit.WEEK.value),
    ("Monthly", CashFlowBucketUnit.MONTH.value),
)


class SetupStep(WizardStep):
    key = "setup"
    title = "Forecast setup"
    subtitle = "Choose the starting date, bucket size, horizon, and scope."

    def __init__(self) -> None:
        super().__init__()
        self._date_edit: QDateEdit | None = None
        self._unit_combo: QComboBox | None = None
        self._count_spin: QSpinBox | None = None
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

        self._unit_combo = QComboBox(root)
        for label, value in _UNIT_LABELS:
            self._unit_combo.addItem(label, value)
        form.addRow("Bucket size", self._unit_combo)

        self._count_spin = QSpinBox(root)
        self._count_spin.setRange(1, 26)
        self._count_spin.setValue(8)
        form.addRow("Number of buckets", self._count_spin)
        outer.addLayout(form)

        self._ar_check = QCheckBox("Include expected receipts (open AR documents)", root)
        self._ar_check.setChecked(True)
        outer.addWidget(self._ar_check)

        self._ap_check = QCheckBox("Include expected payments (open AP documents)", root)
        self._ap_check.setChecked(True)
        outer.addWidget(self._ap_check)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._date_edit is not None:
            existing = state.get(K.KEY_AS_OF_DATE)
            if isinstance(existing, date):
                self._date_edit.setDate(QDate(existing.year, existing.month, existing.day))
        if self._unit_combo is not None:
            existing_unit = state.get(K.KEY_BUCKET_UNIT)
            if isinstance(existing_unit, str):
                idx = self._unit_combo.findData(existing_unit)
                if idx >= 0:
                    self._unit_combo.setCurrentIndex(idx)
        if self._count_spin is not None:
            existing_count = state.get(K.KEY_BUCKET_COUNT)
            if isinstance(existing_count, int) and 1 <= existing_count <= 26:
                self._count_spin.setValue(existing_count)
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
        if self._unit_combo is not None:
            state[K.KEY_BUCKET_UNIT] = str(self._unit_combo.currentData())
        if self._count_spin is not None:
            state[K.KEY_BUCKET_COUNT] = int(self._count_spin.value())
        if self._ar_check is not None:
            state[K.KEY_INCLUDE_AR] = self._ar_check.isChecked()
        if self._ap_check is not None:
            state[K.KEY_INCLUDE_AP] = self._ap_check.isChecked()
        state[K.KEY_FORECAST] = None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_AS_OF_DATE), date):
            return StepValidationResult.fail("Pick an as-of date.")
        if not (state.get(K.KEY_INCLUDE_AR) or state.get(K.KEY_INCLUDE_AP)):
            return StepValidationResult.fail(
                "Select at least one of expected receipts or expected payments."
            )
        return StepValidationResult.ok()
