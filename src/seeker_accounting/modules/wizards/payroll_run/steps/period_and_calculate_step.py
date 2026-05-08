"""Step 1 — Configure the payroll run, then create + calculate it.

This step calls ``payroll_run_service.create_run`` followed immediately by
``calculate_run`` to land on a ``calculated`` run that the next steps can
inspect, approve, and post.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreatePayrollRunCommand,
)
from seeker_accounting.modules.wizards.payroll_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_MONTHS = (
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December"),
)


class PeriodAndCalculateStep(WizardStep):
    key = "period_and_calculate"
    title = "Period & Calculate"
    subtitle = "Define the run, then create and calculate it."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._year: QSpinBox | None = None
        self._month: QComboBox | None = None
        self._label: QLineEdit | None = None
        self._currency: QLineEdit | None = None
        self._run_date: QDateEdit | None = None
        self._payment_date: QDateEdit | None = None
        self._notes: QTextEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        intro = QLabel(
            "Once you advance, the wizard creates a draft run and calculates "
            "all active employees. You can then review headcount and totals.",
            root,
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardMutedText")
        outer.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)

        today = date.today()
        self._year = QSpinBox(root)
        self._year.setRange(2000, 2100)
        self._year.setValue(today.year)
        form.addRow(QLabel("Period year:", root), self._year)

        self._month = QComboBox(root)
        for num, name in _MONTHS:
            self._month.addItem(name, num)
        self._month.setCurrentIndex(today.month - 1)
        form.addRow(QLabel("Period month:", root), self._month)

        self._label = QLineEdit(root)
        self._label.setPlaceholderText("e.g. Monthly Payroll — May 2026")
        form.addRow(QLabel("Run label:", root), self._label)

        self._currency = QLineEdit(root)
        self._currency.setMaxLength(3)
        self._currency.setPlaceholderText("XAF")
        form.addRow(QLabel("Currency code:", root), self._currency)

        self._run_date = QDateEdit(root)
        self._run_date.setCalendarPopup(True)
        self._run_date.setDisplayFormat("yyyy-MM-dd")
        self._run_date.setDate(QDate(today.year, today.month, today.day))
        form.addRow(QLabel("Run date:", root), self._run_date)

        self._payment_date = QDateEdit(root)
        self._payment_date.setCalendarPopup(True)
        self._payment_date.setDisplayFormat("yyyy-MM-dd")
        self._payment_date.setSpecialValueText("(none)")
        self._payment_date.setDate(QDate(today.year, today.month, today.day))
        form.addRow(QLabel("Payment date:", root), self._payment_date)

        self._notes = QTextEdit(root)
        self._notes.setMaximumHeight(60)
        self._notes.setPlaceholderText("Optional notes for the run.")
        form.addRow(QLabel("Notes:", root), self._notes)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        # Pre-fill from prior state, else from active company defaults.
        if self._currency is not None and not self._currency.text().strip():
            ctx = getattr(context.service_registry, "active_company_context", None)
            base = getattr(ctx, "base_currency_code", None) if ctx is not None else None
            self._currency.setText(state.get(K.KEY_CURRENCY_CODE) or base or "XAF")
        if self._label is not None and state.get(K.KEY_RUN_LABEL):
            self._label.setText(str(state.get(K.KEY_RUN_LABEL)))
        if self._year is not None and isinstance(state.get(K.KEY_PERIOD_YEAR), int):
            self._year.setValue(state[K.KEY_PERIOD_YEAR])
        if self._month is not None and isinstance(state.get(K.KEY_PERIOD_MONTH), int):
            idx = self._month.findData(state[K.KEY_PERIOD_MONTH])
            if idx >= 0:
                self._month.setCurrentIndex(idx)

    def write_back(self, state: WizardState) -> None:
        if self._year is not None:
            state[K.KEY_PERIOD_YEAR] = int(self._year.value())
        if self._month is not None:
            state[K.KEY_PERIOD_MONTH] = int(self._month.currentData() or 1)
        if self._label is not None:
            state[K.KEY_RUN_LABEL] = self._label.text().strip()
        if self._currency is not None:
            state[K.KEY_CURRENCY_CODE] = self._currency.text().strip().upper()
        if self._run_date is not None:
            qd = self._run_date.date()
            state[K.KEY_RUN_DATE] = date(qd.year(), qd.month(), qd.day()).isoformat()
        if self._payment_date is not None:
            qd = self._payment_date.date()
            state[K.KEY_PAYMENT_DATE] = date(qd.year(), qd.month(), qd.day()).isoformat()
        if self._notes is not None:
            text = self._notes.toPlainText().strip()
            state[K.KEY_NOTES] = text or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_RUN_LABEL):
            return StepValidationResult.fail("Run label is required.")
        currency = state.get(K.KEY_CURRENCY_CODE)
        if not currency or len(currency) != 3:
            return StepValidationResult.fail("Currency code must be a 3-letter ISO code.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_RUN_ID):
            return
        company_id = context.require_company_id()
        service = context.service_registry.payroll_run_service

        run_date = date.fromisoformat(state[K.KEY_RUN_DATE])
        payment_date_raw = state.get(K.KEY_PAYMENT_DATE)
        payment_date = date.fromisoformat(payment_date_raw) if payment_date_raw else None

        cmd = CreatePayrollRunCommand(
            period_year=int(state[K.KEY_PERIOD_YEAR]),
            period_month=int(state[K.KEY_PERIOD_MONTH]),
            run_label=str(state[K.KEY_RUN_LABEL]),
            currency_code=str(state[K.KEY_CURRENCY_CODE]),
            run_date=run_date,
            payment_date=payment_date,
            notes=state.get(K.KEY_NOTES),
        )
        run = service.create_run(company_id, cmd)
        state[K.KEY_RUN_ID] = run.id
        state[K.KEY_RUN_REFERENCE] = run.run_reference
        state[K.KEY_RUN_STATUS] = run.status_code

        calculated = service.calculate_run(company_id, run.id)
        state[K.KEY_RUN_STATUS] = calculated.status_code

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        ref = state.get(K.KEY_RUN_REFERENCE)
        if ref:
            return f"Created and calculated payroll run {ref} (status {state.get(K.KEY_RUN_STATUS)})."
        label = state.get(K.KEY_RUN_LABEL) or "(unlabeled)"
        year = state.get(K.KEY_PERIOD_YEAR)
        month = state.get(K.KEY_PERIOD_MONTH)
        return f"Create payroll run \u201c{label}\u201d for {year}-{month:02d} and calculate."
