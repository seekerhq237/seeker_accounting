"""Step 1 — Pick the OPEN fiscal period to close."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
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


class PeriodSelectionStep(WizardStep):
    key = "period_selection"
    title = "Select Period"
    subtitle = "Choose the fiscal period to close."

    def __init__(self) -> None:
        super().__init__()
        self._combo: QComboBox | None = None
        self._summary: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        intro = QLabel(
            "Only OPEN periods are listed. Closing prevents new postings to "
            "the period; you can reopen it later if needed (subject to "
            "permission).",
            root,
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #4E5866; font-size: 11px;")
        outer.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        self._combo = QComboBox(root)
        self._combo.setMinimumWidth(280)
        form.addRow(QLabel("Period to close:", root), self._combo)
        outer.addLayout(form)

        self._summary = QLabel("", root)
        self._summary.setStyleSheet("color: #2E3848; font-size: 12px;")
        self._summary.setWordWrap(True)
        outer.addWidget(self._summary)
        outer.addStretch(1)

        self._combo.currentIndexChanged.connect(self._refresh_summary)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._combo is None:
            return
        company_id = context.require_company_id()
        service = context.service_registry.fiscal_calendar_service
        periods = service.list_periods(company_id)
        open_periods = [p for p in periods if p.status_code == "OPEN"]
        open_periods.sort(key=lambda p: p.start_date)

        self._combo.blockSignals(True)
        self._combo.clear()
        for p in open_periods:
            label = f"{p.period_code} — {p.period_name} ({p.start_date.isoformat()} → {p.end_date.isoformat()})"
            self._combo.addItem(label, p.id)
        # Pre-select prior selection or first open period.
        prior = state.get(K.KEY_PERIOD_ID)
        if isinstance(prior, int):
            idx = self._combo.findData(prior)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        if self._combo is None or self._summary is None:
            return
        if self._combo.count() == 0:
            self._summary.setText("No OPEN periods are available to close.")
            return
        self._summary.setText(self._combo.currentText())

    def write_back(self, state: WizardState) -> None:
        if self._combo is None or self._combo.count() == 0:
            return
        period_id = self._combo.currentData()
        if period_id is None:
            return
        text = self._combo.currentText()
        # Format: "<code> — <name> (<start> → <end>)"
        code = text.split(" — ", 1)[0]
        state[K.KEY_PERIOD_ID] = int(period_id)
        state[K.KEY_PERIOD_CODE] = code
        state[K.KEY_PERIOD_STATUS_CODE] = "OPEN"

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if self._combo is None or self._combo.count() == 0:
            return StepValidationResult.fail("There are no OPEN periods to close.")
        if state.get(K.KEY_PERIOD_ID) is None:
            return StepValidationResult.fail("Pick a period before continuing.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        code = state.get(K.KEY_PERIOD_CODE)
        if not code:
            return None
        return f"Close fiscal period {code}."
