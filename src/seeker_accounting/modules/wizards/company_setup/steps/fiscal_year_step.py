"""Step 2 — Fiscal year + monthly periods."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QGridLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.wizards.company_setup import state_keys as K
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.forms import create_field_block


class FiscalYearStep(WizardStep):
    key = "fiscal_year"
    title = "Fiscal Year"
    subtitle = "Define the opening fiscal year. Twelve monthly periods will be generated."
    commits_on_advance = True

    # ── UI ──────────────────────────────────────────────────────────────

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        today = date.today()

        self._code_edit = QLineEdit(root)
        self._code_edit.setPlaceholderText(f"FY{today.year}")
        grid.addWidget(create_field_block("Year Code", self._code_edit), 0, 0)

        self._name_edit = QLineEdit(root)
        self._name_edit.setPlaceholderText(f"Fiscal Year {today.year}")
        grid.addWidget(create_field_block("Display Name", self._name_edit), 0, 1)

        self._start_edit = QDateEdit(root)
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd")
        self._start_edit.setDate(QDate(today.year, 1, 1))
        grid.addWidget(create_field_block("Start Date", self._start_edit), 1, 0)

        self._end_edit = QDateEdit(root)
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd")
        self._end_edit.setDate(QDate(today.year, 12, 31))
        grid.addWidget(create_field_block("End Date", self._end_edit), 1, 1)

        layout.addLayout(grid)

        helper = QLabel(
            "On finish, twelve monthly periods (OPEN) will be generated for this "
            "fiscal year. You can lock or close periods later from Fiscal Periods.",
            root,
        )
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #4E5866; font-size: 11px;")
        layout.addWidget(helper)
        layout.addStretch(1)
        return root

    # ── Hooks ───────────────────────────────────────────────────────────

    def load(self, context: WizardContext, state: WizardState) -> None:
        if not self._code_edit.text():
            today = date.today()
            self._code_edit.setText(state.get(K.KEY_FISCAL_YEAR_CODE, f"FY{today.year}"))
            self._name_edit.setText(state.get(K.KEY_FISCAL_YEAR_NAME, f"Fiscal Year {today.year}"))

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        errors: dict[str, str] = {}
        code = self._code_edit.text().strip()
        name = self._name_edit.text().strip()
        start = self._start_edit.date().toPython()
        end = self._end_edit.date().toPython()
        if not code:
            errors["Year Code"] = "is required."
        if not name:
            errors["Display Name"] = "is required."
        if start >= end:
            errors["Date Range"] = "Start date must be before end date."
        if errors:
            return StepValidationResult.fail(field_errors=errors)
        return StepValidationResult.ok()

    def write_back(self, state: WizardState) -> None:
        state[K.KEY_FISCAL_YEAR_CODE] = self._code_edit.text().strip()
        state[K.KEY_FISCAL_YEAR_NAME] = self._name_edit.text().strip()
        state[K.KEY_FISCAL_YEAR_START] = self._start_edit.date().toString("yyyy-MM-dd")
        state[K.KEY_FISCAL_YEAR_END] = self._end_edit.date().toString("yyyy-MM-dd")

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if state.get(K.KEY_FISCAL_PERIODS_GENERATED):
            return
        company_id = context.require_company_id()
        service = context.service_registry.fiscal_calendar_service
        start = date.fromisoformat(state[K.KEY_FISCAL_YEAR_START])
        end = date.fromisoformat(state[K.KEY_FISCAL_YEAR_END])
        try:
            year_dto = service.create_fiscal_year(
                company_id,
                CreateFiscalYearCommand(
                    year_code=state[K.KEY_FISCAL_YEAR_CODE],
                    year_name=state[K.KEY_FISCAL_YEAR_NAME],
                    start_date=start,
                    end_date=end,
                    status_code="OPEN",
                ),
            )
        except (ValidationError, ConflictError):
            raise
        state[K.KEY_FISCAL_YEAR_ID] = year_dto.id
        try:
            calendar = service.generate_periods(
                company_id,
                year_dto.id,
                GenerateFiscalPeriodsCommand(periods_per_year=12, opening_status_code="OPEN"),
            )
        except (ValidationError, ConflictError):
            raise
        state[K.KEY_FISCAL_PERIODS_GENERATED] = len(calendar.periods)

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        return (
            f"Open fiscal year {state.get(K.KEY_FISCAL_YEAR_CODE, '—')} "
            f"({state.get(K.KEY_FISCAL_YEAR_START)} → {state.get(K.KEY_FISCAL_YEAR_END)}) "
            "and generate 12 monthly periods."
        )
