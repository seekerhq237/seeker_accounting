"""Step 1 — Choose run date and period-end date, then create the draft run.

Creating the run computes per-asset depreciation for the chosen period_end_date
so the next step can preview and confirm.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.fixed_assets.dto.depreciation_commands import (
    CreateDepreciationRunCommand,
)
from seeker_accounting.modules.wizards.depreciation_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class CreateRunStep(WizardStep):
    key = "create_run"
    title = "Period & Compute"
    subtitle = "Pick the period-end date, then compute depreciation."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._run_date: QDateEdit | None = None
        self._period_end: QDateEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        intro = QLabel(
            "Choose the period-end date \u2014 typically the last day of the month. "
            "All active depreciable assets will be charged for the period.",
            root,
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardMutedText")
        outer.addWidget(intro)

        form = QFormLayout()
        today = date.today()
        self._run_date = QDateEdit(root)
        self._run_date.setCalendarPopup(True)
        self._run_date.setDisplayFormat("yyyy-MM-dd")
        self._run_date.setDate(QDate(today.year, today.month, today.day))
        form.addRow(QLabel("Run date:", root), self._run_date)

        self._period_end = QDateEdit(root)
        self._period_end.setCalendarPopup(True)
        self._period_end.setDisplayFormat("yyyy-MM-dd")
        self._period_end.setDate(QDate(today.year, today.month, today.day))
        form.addRow(QLabel("Period end date:", root), self._period_end)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        for key, widget in ((K.KEY_RUN_DATE, self._run_date), (K.KEY_PERIOD_END_DATE, self._period_end)):
            raw = state.get(key)
            if raw and widget is not None:
                try:
                    d = date.fromisoformat(str(raw))
                    widget.setDate(QDate(d.year, d.month, d.day))
                except ValueError:
                    pass

    def write_back(self, state: WizardState) -> None:
        if self._run_date is not None:
            qd = self._run_date.date()
            state[K.KEY_RUN_DATE] = date(qd.year(), qd.month(), qd.day()).isoformat()
        if self._period_end is not None:
            qd = self._period_end.date()
            state[K.KEY_PERIOD_END_DATE] = date(qd.year(), qd.month(), qd.day()).isoformat()

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        try:
            run_d = date.fromisoformat(str(state.get(K.KEY_RUN_DATE)))
            end_d = date.fromisoformat(str(state.get(K.KEY_PERIOD_END_DATE)))
        except (TypeError, ValueError):
            return StepValidationResult.fail("Pick valid run and period-end dates.")
        if end_d > run_d:
            return StepValidationResult.fail("Period-end date cannot be after the run date.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_RUN_ID), int):
            return
        company_id = context.require_company_id()
        cmd = CreateDepreciationRunCommand(
            run_date=date.fromisoformat(str(state[K.KEY_RUN_DATE])),
            period_end_date=date.fromisoformat(str(state[K.KEY_PERIOD_END_DATE])),
        )
        run = context.service_registry.depreciation_run_service.create_run(company_id, cmd)
        state[K.KEY_RUN_ID] = run.id
        state[K.KEY_RUN_NUMBER] = run.run_number
        state[K.KEY_RUN_STATUS] = run.status_code
        state[K.KEY_ASSET_COUNT] = run.asset_count
        state[K.KEY_TOTAL_DEPRECIATION] = str(run.total_depreciation)

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        if state.get(K.KEY_RUN_ID):
            return f"Draft run created with {state.get(K.KEY_ASSET_COUNT)} asset(s)."
        end = state.get(K.KEY_PERIOD_END_DATE) or "(unset)"
        return f"Compute depreciation through {end}."
