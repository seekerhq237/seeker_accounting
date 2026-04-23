"""Compact guided wizard: create a fiscal year and generate its periods in one flow."""

from __future__ import annotations

from calendar import month_name
from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_dto import (
    FiscalCalendarDTO,
    FiscalYearDTO,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


@dataclass(frozen=True, slots=True)
class FiscalYearSetupWizardResult:
    """Returned by the wizard on successful completion."""

    fiscal_year: FiscalYearDTO
    period_count: int
    summary: str


@dataclass(frozen=True, slots=True)
class _PeriodPreview:
    number: int
    code: str
    name: str
    start_date: date
    end_date: date


class FiscalYearSetupWizardDialog(BaseDialog):
    """Three-step guided dialog:

    1. **Year** — capture year code, name, and boundary dates (with sensible defaults).
    2. **Review** — show the 12 monthly periods that will be generated and let the user confirm.
    3. **Done** — success summary after the fiscal year and its periods are created.

    Performs ``create_fiscal_year`` + ``generate_periods`` in sequence. On any failure the
    message surfaces inline and the user stays on the review step.
    """

    _STEP_LABELS = ("1. Year", "2. Review", "3. Done")

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._service_registry = service_registry
        self._company_id = company_id
        self._company_name = company_name
        self._result: FiscalYearSetupWizardResult | None = None
        self._current_step = 0

        super().__init__("Fiscal Year Setup", parent, help_key="wizard.fiscal_year_setup")
        self.setObjectName("FiscalYearSetupWizardDialog")
        self.resize(640, 540)

        intro = QLabel(
            "Create a fiscal year and generate its 12 monthly periods in one guided flow.",
            self,
        )
        intro.setObjectName("PageSummary")
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        self.body_layout.addWidget(create_label_value_row("Company", company_name, self))

        self.body_layout.addWidget(self._build_step_header())

        self._error_label = QLabel(self)
        self._error_label.setObjectName("DialogErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self.body_layout.addWidget(self._error_label)

        self.body_layout.addWidget(self._build_stack(), 1)

        self._build_buttons()
        self._load_defaults()
        self._update_step_pills()
        self._update_buttons()

    # ── Public API ─────────────────────────────────────────────────────

    @property
    def result_payload(self) -> FiscalYearSetupWizardResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> FiscalYearSetupWizardResult | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog.exec()
        return dialog.result_payload

    # ── Step header ────────────────────────────────────────────────────

    def _build_step_header(self) -> QWidget:
        header = QWidget(self)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._step_pills: list[QLabel] = []
        for text in self._STEP_LABELS:
            pill = QLabel(text, header)
            pill.setObjectName("WizardStepPill")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(pill)
            self._step_pills.append(pill)
        layout.addStretch(1)
        return header

    # ── Step stack ─────────────────────────────────────────────────────

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_year_page())
        self._stack.addWidget(self._build_review_page())
        self._stack.addWidget(self._build_done_page())
        return self._stack

    def _build_year_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame(page)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(10)

        title = QLabel("Fiscal Year Definition", card)
        title.setObjectName("DialogSectionTitle")
        card_layout.addWidget(title)

        hint = QLabel(
            "Defaults suggest the current calendar year. Change them to match your fiscal policy.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._year_code_edit = QLineEdit(card)
        self._year_code_edit.setPlaceholderText("FY2026")
        self._year_code_edit.textChanged.connect(self._on_inputs_changed)
        grid.addWidget(create_field_block("Year Code", self._year_code_edit), 0, 0)

        self._year_name_edit = QLineEdit(card)
        self._year_name_edit.setPlaceholderText("Fiscal Year 2026")
        self._year_name_edit.textChanged.connect(self._on_inputs_changed)
        grid.addWidget(create_field_block("Year Name", self._year_name_edit), 0, 1)

        self._start_date_edit = QDateEdit(card)
        self._start_date_edit.setCalendarPopup(True)
        self._start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._start_date_edit.dateChanged.connect(self._on_inputs_changed)
        grid.addWidget(create_field_block("Start Date", self._start_date_edit), 1, 0)

        self._end_date_edit = QDateEdit(card)
        self._end_date_edit.setCalendarPopup(True)
        self._end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._end_date_edit.dateChanged.connect(self._on_inputs_changed)
        grid.addWidget(create_field_block("End Date", self._end_date_edit), 1, 1)

        card_layout.addLayout(grid)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame(page)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(10)

        title = QLabel("Period Preview", card)
        title.setObjectName("DialogSectionTitle")
        card_layout.addWidget(title)

        self._review_summary = QLabel("", card)
        self._review_summary.setObjectName("DialogSectionSummary")
        self._review_summary.setWordWrap(True)
        card_layout.addWidget(self._review_summary)

        self._preview_table = QTableWidget(card)
        self._preview_table.setColumnCount(4)
        self._preview_table.setHorizontalHeaderLabels(("#", "Code", "Name", "Date Range"))
        configure_compact_table(self._preview_table)
        self._preview_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview_table.verticalHeader().setVisible(False)
        card_layout.addWidget(self._preview_table, 1)

        footer = QLabel(
            "Only monthly periods are supported in this pass. Adjustment periods are not generated.",
            card,
        )
        footer.setObjectName("DialogSectionFooter")
        footer.setWordWrap(True)
        card_layout.addWidget(footer)

        layout.addWidget(card, 1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame(page)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 18)
        card_layout.setSpacing(10)

        title = QLabel("Fiscal year ready", card)
        title.setObjectName("DialogSectionTitle")
        card_layout.addWidget(title)

        self._done_summary = QLabel("", card)
        self._done_summary.setObjectName("DialogSectionSummary")
        self._done_summary.setWordWrap(True)
        card_layout.addWidget(self._done_summary)

        card_layout.addStretch(1)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    # ── Buttons ────────────────────────────────────────────────────────

    def _build_buttons(self) -> None:
        self.button_box.setStandardButtons(QDialogButtonBox.StandardButton.NoButton)

        self._back_button = QPushButton("Back", self)
        self._back_button.setProperty("variant", "secondary")
        self._back_button.clicked.connect(self._go_back)
        self.button_box.addButton(self._back_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._next_button = QPushButton("Next", self)
        self._next_button.setProperty("variant", "primary")
        self._next_button.clicked.connect(self._go_next)
        self.button_box.addButton(self._next_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._apply_button = QPushButton("Create Fiscal Year", self)
        self._apply_button.setProperty("variant", "primary")
        self._apply_button.clicked.connect(self._handle_apply)
        self.button_box.addButton(self._apply_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._close_button = QPushButton("Cancel", self)
        self._close_button.setProperty("variant", "ghost")
        self._close_button.clicked.connect(self.reject)
        self.button_box.addButton(self._close_button, QDialogButtonBox.ButtonRole.RejectRole)

    # ── Defaults / inputs ──────────────────────────────────────────────

    def _load_defaults(self) -> None:
        today = date.today()
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
        self._year_code_edit.setText(f"FY{today.year}")
        self._year_name_edit.setText(f"Fiscal Year {today.year}")
        self._start_date_edit.setDate(QDate(start.year, start.month, start.day))
        self._end_date_edit.setDate(QDate(end.year, end.month, end.day))

    def _on_inputs_changed(self, *_args: object) -> None:
        self._set_error(None)

    # ── Navigation ─────────────────────────────────────────────────────

    def _go_next(self) -> None:
        if self._current_step == 0:
            if not self._validate_year_inputs():
                return
            if not self._refresh_preview():
                return
        self._current_step += 1
        self._stack.setCurrentIndex(self._current_step)
        self._update_step_pills()
        self._update_buttons()

    def _go_back(self) -> None:
        if self._current_step <= 0:
            return
        self._current_step -= 1
        self._stack.setCurrentIndex(self._current_step)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _update_step_pills(self) -> None:
        for index, pill in enumerate(self._step_pills):
            if index < self._current_step:
                pill.setProperty("completed", "true")
                pill.setProperty("current", "false")
            elif index == self._current_step:
                pill.setProperty("completed", "false")
                pill.setProperty("current", "true")
            else:
                pill.setProperty("completed", "false")
                pill.setProperty("current", "false")
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _update_buttons(self) -> None:
        on_year = self._current_step == 0
        on_review = self._current_step == 1
        on_done = self._current_step == 2

        self._back_button.setVisible(on_review)
        self._next_button.setVisible(on_year)
        self._apply_button.setVisible(on_review)
        self._close_button.setText("Close" if on_done else "Cancel")

    # ── Step 1 validation ──────────────────────────────────────────────

    def _validate_year_inputs(self) -> bool:
        year_code = self._year_code_edit.text().strip()
        if not year_code:
            self._set_error("Year code is required.")
            self._year_code_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return False
        year_name = self._year_name_edit.text().strip()
        if not year_name:
            self._set_error("Year name is required.")
            self._year_name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return False
        start = self._start_date_edit.date().toPython()
        end = self._end_date_edit.date().toPython()
        if start >= end:
            self._set_error("Fiscal year start date must be before end date.")
            return False
        return True

    # ── Preview computation (mirrors service logic for display only) ──

    def _refresh_preview(self) -> bool:
        start = self._start_date_edit.date().toPython()
        end = self._end_date_edit.date().toPython()
        year_code = self._year_code_edit.text().strip()
        try:
            periods = self._compute_monthly_periods(year_code, start, end)
        except ValueError as exc:
            self._set_error(str(exc))
            return False

        self._preview_table.setRowCount(len(periods))
        for row, period in enumerate(periods):
            self._preview_table.setItem(row, 0, QTableWidgetItem(str(period.number)))
            self._preview_table.setItem(row, 1, QTableWidgetItem(period.code))
            self._preview_table.setItem(row, 2, QTableWidgetItem(period.name))
            self._preview_table.setItem(
                row,
                3,
                QTableWidgetItem(f"{period.start_date.isoformat()} → {period.end_date.isoformat()}"),
            )
        self._preview_table.resizeColumnsToContents()

        year_name = self._year_name_edit.text().strip()
        self._review_summary.setText(
            f"{year_name or year_code}: {len(periods)} monthly periods "
            f"from {start.isoformat()} to {end.isoformat()}."
        )
        return True

    @staticmethod
    def _compute_monthly_periods(
        year_code: str, start: date, end: date
    ) -> list[_PeriodPreview]:
        """Mirror of ``FiscalCalendarService._build_monthly_periods`` for preview only."""
        periods: list[_PeriodPreview] = []
        current_start = start
        for number in range(1, 13):
            if number == 12:
                current_end = end
            else:
                next_start = _add_months(current_start, 1)
                current_end = next_start - timedelta(days=1)
                if current_end > end:
                    raise ValueError(
                        "Fiscal year dates do not align cleanly with monthly period generation."
                    )
            periods.append(
                _PeriodPreview(
                    number=number,
                    code=f"{year_code}-{number:02d}" if year_code else f"P{number:02d}",
                    name=f"{month_name[current_start.month]} {current_start.year}",
                    start_date=current_start,
                    end_date=current_end,
                )
            )
            current_start = current_end + timedelta(days=1)

        if periods[-1].end_date != end:
            raise ValueError("Generated periods do not cover the fiscal year cleanly.")
        return periods

    # ── Apply ──────────────────────────────────────────────────────────

    def _handle_apply(self) -> None:
        self._set_error(None)
        self._apply_button.setEnabled(False)
        try:
            fiscal_year = self._create_fiscal_year()
            if fiscal_year is None:
                return
            calendar = self._generate_periods(fiscal_year.id)
            if calendar is None:
                return
        finally:
            self._apply_button.setEnabled(True)

        period_count = len(calendar.periods)
        summary = (
            f"Fiscal year {fiscal_year.year_code} created with {period_count} monthly periods "
            f"covering {fiscal_year.start_date.isoformat()} to {fiscal_year.end_date.isoformat()}."
        )
        self._result = FiscalYearSetupWizardResult(
            fiscal_year=calendar.fiscal_year,
            period_count=period_count,
            summary=summary,
        )
        self._done_summary.setText(summary)

        self._current_step = 2
        self._stack.setCurrentIndex(self._current_step)
        self._update_step_pills()
        self._update_buttons()

    def _create_fiscal_year(self) -> FiscalYearDTO | None:
        command = CreateFiscalYearCommand(
            year_code=self._year_code_edit.text().strip(),
            year_name=self._year_name_edit.text().strip(),
            start_date=self._start_date_edit.date().toPython(),
            end_date=self._end_date_edit.date().toPython(),
        )
        try:
            return self._service_registry.fiscal_calendar_service.create_fiscal_year(
                self._company_id, command
            )
        except (ValidationError, ConflictError, PermissionDeniedError) as exc:
            self._set_error(str(exc))
            return None

    def _generate_periods(self, fiscal_year_id: int) -> FiscalCalendarDTO | None:
        try:
            return self._service_registry.fiscal_calendar_service.generate_periods(
                self._company_id,
                fiscal_year_id,
                GenerateFiscalPeriodsCommand(),
            )
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
            self._set_error(
                f"Fiscal year was created but period generation failed: {exc}"
            )
            return None

    # ── Helpers ────────────────────────────────────────────────────────

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()

    def accept(self) -> None:  # type: ignore[override]
        super().accept()


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = value.day
    while day > 0:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    raise ValueError("Fiscal year dates do not support monthly period generation.")
