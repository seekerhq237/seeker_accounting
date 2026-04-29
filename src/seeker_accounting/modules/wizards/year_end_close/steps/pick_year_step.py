"""Step 1 — Pick the fiscal year to close."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.year_end_close import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class PickYearStep(WizardStep):
    key = "pick_year"
    title = "Select fiscal year"
    subtitle = "Pick a fiscal year that is currently OPEN."

    def __init__(self) -> None:
        super().__init__()
        self._combo: QComboBox | None = None
        self._info: QLabel | None = None
        self._populated_once = False

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()
        self._combo = QComboBox(root)
        form.addRow(QLabel("Fiscal year:", root), self._combo)
        outer.addLayout(form)
        self._info = QLabel(
            "Closing a fiscal year is a controlled transition. All periods must be "
            "CLOSED or LOCKED before the year can be closed.",
            root,
        )
        self._info.setWordWrap(True)
        outer.addWidget(self._info)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._combo is None or self._populated_once:
            return
        self._combo.clear()
        company_id = context.require_company_id()
        try:
            years = context.service_registry.fiscal_calendar_service.list_fiscal_years(
                company_id
            )
        except Exception:
            years = []
        # Only show years that are not already CLOSED.
        for y in years:
            if y.status_code == "CLOSED":
                continue
            label = f"{y.year_code} — {y.year_name} ({y.start_date} → {y.end_date}) [{y.status_code}]"
            self._combo.addItem(label, int(y.id))
        # Pre-select state value if any.
        existing = state.get(K.KEY_FISCAL_YEAR_ID)
        if isinstance(existing, int):
            idx = self._combo.findData(existing)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        self._populated_once = True

    def write_back(self, state: WizardState) -> None:
        if self._combo is None:
            return
        data = self._combo.currentData()
        if isinstance(data, int):
            state[K.KEY_FISCAL_YEAR_ID] = int(data)
            state[K.KEY_FISCAL_YEAR_CODE] = self._combo.currentText().split(" — ", 1)[0]
        else:
            state[K.KEY_FISCAL_YEAR_ID] = None
            state[K.KEY_FISCAL_YEAR_CODE] = None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_FISCAL_YEAR_ID), int):
            return StepValidationResult.fail(
                "Pick a fiscal year. If none are listed, no closeable year exists."
            )
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        return state.get(K.KEY_FISCAL_YEAR_CODE)
