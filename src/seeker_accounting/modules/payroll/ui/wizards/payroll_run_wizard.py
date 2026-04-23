"""PayrollRunWizardDialog — guided payroll run flow.

Orchestrates the create → calculate → review → approve lifecycle for a
single payroll run. Existing expert controls (`New Run`, `Calculate`,
`Approve`) remain on the ribbon as fast-path alternatives.

Steps:

1. **Period**      — period year/month, label, currency, dates.
2. **Readiness**   — calls ``payroll_validation_service.validate_for_period``
                     and shows blockers + warnings; user may cancel or
                     continue if no errors are present.
3. **Inputs**      — lists approved variable-input batches for the period
                     (read-only; the wizard does not create or approve
                     batches on the fly).
4. **Calculate**   — creates the run (draft) and calculates it.
                     Shows per-employee totals table.
5. **Variance**    — compares per-employee net against the most recent
                     prior calculated/approved/posted run; anomalies
                     (>±10%) require acknowledgement.
6. **Inclusion**   — optional include/exclude per employee with a reason.
                     Exclusions persist via ``set_run_employee_inclusion``
                     and are honoured by posting and payment services.
7. **Approve**     — optional approval step. User may approve now or
                     defer.
8. **Done**        — summary with handoff hints (posting / printing).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreatePayrollRunCommand,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog
from seeker_accounting.shared.ui.forms import create_field_block, create_label_value_row


_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PayrollRunWizardResult:
    run_id: int
    run_reference: str
    period_year: int
    period_month: int
    status_code: str          # "calculated" or "approved"
    employee_count: int
    total_gross: float
    total_net: float
    approved: bool
    summary: str


class PayrollRunWizardDialog(BaseDialog):
    """5-step guided payroll run dialog — see module docstring."""

    _STEP_LABELS = (
        "1. Period",
        "2. Readiness",
        "3. Inputs",
        "4. Calculate",
        "5. Variance",
        "6. Inclusion",
        "7. Approve",
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> None:
        self._registry = service_registry
        self._company_id = company_id
        self._company_name = company_name

        self._validation_result = None
        self._input_batches: list = []
        self._created_run = None
        self._calculated_run = None
        self._run_employees: list = []
        self._approved = False
        self._result: PayrollRunWizardResult | None = None
        self._current_step = 0

        super().__init__(
            "Payroll Run",
            parent,
            help_key="wizard.payroll_run",
        )
        self.setObjectName("PayrollRunWizardDialog")
        self.resize(820, 660)

        intro = QLabel(
            "Create, calculate and approve a payroll run for a period in a "
            "single guided flow. Expert controls remain available on the "
            "ribbon.",
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

    # ── Public API ────────────────────────────────────────────────────

    @property
    def result_payload(self) -> PayrollRunWizardResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> PayrollRunWizardResult | None:
        dialog = cls(service_registry, company_id, company_name, parent=parent)
        dialog.exec()
        return dialog.result_payload

    # ── Header ────────────────────────────────────────────────────────

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

    # ── Stack ─────────────────────────────────────────────────────────

    def _build_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_period_page())
        self._stack.addWidget(self._build_readiness_page())
        self._stack.addWidget(self._build_inputs_page())
        self._stack.addWidget(self._build_calculate_page())
        self._stack.addWidget(self._build_variance_page())
        self._stack.addWidget(self._build_inclusion_page())
        self._stack.addWidget(self._build_approve_page())
        self._stack.addWidget(self._build_done_page())
        return self._stack

    def _build_period_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Run Period")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        today = date.today()

        self._period_year_spin = QSpinBox(card)
        self._period_year_spin.setRange(2000, 2100)
        self._period_year_spin.setValue(today.year)
        grid.addWidget(create_field_block("Period Year *", self._period_year_spin), 0, 0)

        self._period_month_spin = QSpinBox(card)
        self._period_month_spin.setRange(1, 12)
        self._period_month_spin.setValue(today.month)
        grid.addWidget(create_field_block("Period Month *", self._period_month_spin), 0, 1)

        self._label_edit = QLineEdit(card)
        self._label_edit.setPlaceholderText("e.g. Monthly Payroll")
        grid.addWidget(create_field_block("Run Label *", self._label_edit), 1, 0)

        self._currency_edit = QLineEdit(card)
        self._currency_edit.setPlaceholderText("XAF")
        grid.addWidget(create_field_block("Currency *", self._currency_edit), 1, 1)

        self._run_date_edit = QDateEdit(card)
        self._run_date_edit.setCalendarPopup(True)
        self._run_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._run_date_edit.setDate(QDate(today.year, today.month, today.day))
        grid.addWidget(create_field_block("Run Date *", self._run_date_edit), 2, 0)

        self._payment_date_edit = QDateEdit(card)
        self._payment_date_edit.setCalendarPopup(True)
        self._payment_date_edit.setDisplayFormat("yyyy-MM-dd")
        self._payment_date_edit.setDate(QDate(today.year, today.month, today.day))
        self._payment_date_edit.setSpecialValueText("—")
        grid.addWidget(create_field_block("Payment Date", self._payment_date_edit), 2, 1)

        card.layout().addLayout(grid)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_readiness_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Readiness Scan")

        self._readiness_summary_label = QLabel(card)
        self._readiness_summary_label.setObjectName("DialogSectionSummary")
        self._readiness_summary_label.setWordWrap(True)
        card.layout().addWidget(self._readiness_summary_label)

        self._issues_table = QTableWidget(0, 3, card)
        self._issues_table.setHorizontalHeaderLabels(["Severity", "Employee", "Message"])
        self._issues_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._issues_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._issues_table.verticalHeader().setVisible(False)
        self._issues_table.horizontalHeader().setStretchLastSection(True)
        self._issues_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._issues_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        card.layout().addWidget(self._issues_table, 1)

        self._readiness_acknowledge = QCheckBox(
            "I acknowledge remaining warnings and want to continue.",
            card,
        )
        self._readiness_acknowledge.hide()
        card.layout().addWidget(self._readiness_acknowledge)

        outer.addWidget(card, 1)
        return page

    def _build_inputs_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Approved Variable Inputs")

        self._inputs_hint_label = QLabel(card)
        self._inputs_hint_label.setObjectName("DialogSectionSummary")
        self._inputs_hint_label.setWordWrap(True)
        card.layout().addWidget(self._inputs_hint_label)

        self._inputs_table = QTableWidget(0, 4, card)
        self._inputs_table.setHorizontalHeaderLabels(
            ["Reference", "Label", "Status", "Lines"]
        )
        self._inputs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._inputs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._inputs_table.verticalHeader().setVisible(False)
        self._inputs_table.horizontalHeader().setStretchLastSection(False)
        hdr = self._inputs_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        card.layout().addWidget(self._inputs_table, 1)

        outer.addWidget(card, 1)
        return page

    def _build_calculate_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        totals_card = self._card("Calculation Totals")
        self._totals_label = QLabel(totals_card)
        self._totals_label.setObjectName("DialogSectionSummary")
        self._totals_label.setWordWrap(True)
        totals_card.layout().addWidget(self._totals_label)
        outer.addWidget(totals_card)

        results_card = self._card("Per-Employee Results")
        self._employees_table = QTableWidget(0, 5, results_card)
        self._employees_table.setHorizontalHeaderLabels(
            ["Employee", "Gross", "Deductions", "Taxes", "Net"]
        )
        self._employees_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._employees_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._employees_table.verticalHeader().setVisible(False)
        hdr = self._employees_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        results_card.layout().addWidget(self._employees_table, 1)
        outer.addWidget(results_card, 1)

        return page

    def _build_variance_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        summary_card = self._card("Variance vs Prior Period")
        self._variance_summary_label = QLabel(summary_card)
        self._variance_summary_label.setObjectName("DialogSectionSummary")
        self._variance_summary_label.setWordWrap(True)
        summary_card.layout().addWidget(self._variance_summary_label)
        outer.addWidget(summary_card)

        table_card = self._card("Per-Employee Variance")
        self._variance_table = QTableWidget(0, 5, table_card)
        self._variance_table.setHorizontalHeaderLabels(
            ["Employee", "Prior Net", "Current Net", "Δ", "Δ %"]
        )
        self._variance_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._variance_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._variance_table.verticalHeader().setVisible(False)
        hdr = self._variance_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        table_card.layout().addWidget(self._variance_table, 1)
        outer.addWidget(table_card, 1)

        self._variance_ack = QCheckBox(
            "I have reviewed anomalies (>10% change flagged) and want to continue.",
            page,
        )
        self._variance_ack.hide()
        outer.addWidget(self._variance_ack)
        return page

    def _build_inclusion_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        summary_card = self._card("Include or Exclude Employees")
        self._inclusion_summary_label = QLabel(summary_card)
        self._inclusion_summary_label.setObjectName("DialogSectionSummary")
        self._inclusion_summary_label.setWordWrap(True)
        self._inclusion_summary_label.setText(
            "Double-click an employee row to toggle inclusion. Excluded "
            "employees keep their calculated amounts on file but are skipped "
            "by posting, payments and payslip printing. A reason is required "
            "when excluding."
        )
        summary_card.layout().addWidget(self._inclusion_summary_label)
        outer.addWidget(summary_card)

        table_card = self._card("Employees")
        self._inclusion_table = QTableWidget(0, 5, table_card)
        self._inclusion_table.setHorizontalHeaderLabels(
            ["Included", "Employee", "Net Payable", "Status", "Reason"]
        )
        self._inclusion_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._inclusion_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._inclusion_table.verticalHeader().setVisible(False)
        hdr = self._inclusion_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._inclusion_table.cellDoubleClicked.connect(self._on_inclusion_toggle_row)
        table_card.layout().addWidget(self._inclusion_table, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._toggle_inclusion_button = QPushButton("Toggle Selected", table_card)
        self._toggle_inclusion_button.setProperty("variant", "secondary")
        self._toggle_inclusion_button.clicked.connect(self._on_inclusion_toggle_selected)
        button_row.addWidget(self._toggle_inclusion_button)
        table_card.layout().addLayout(button_row)
        outer.addWidget(table_card, 1)
        return page

    # ── Step: Inclusion ───────────────────────────────────────────────

    def _refresh_inclusion(self) -> None:
        """Repopulate the inclusion table from the latest run_employees list."""
        try:
            self._run_employees = self._registry.payroll_run_service.list_run_employees(
                self._company_id, self._calculated_run.id
            )
        except Exception:  # noqa: BLE001
            # Fall back to in-memory list if service call fails.
            pass
        self._inclusion_table.setRowCount(len(self._run_employees))
        included_count = 0
        for row, emp in enumerate(self._run_employees):
            is_included = (emp.status_code or "").lower() == "included"
            if is_included:
                included_count += 1

            flag_item = QTableWidgetItem("✓" if is_included else "—")
            flag_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            flag_item.setData(Qt.ItemDataRole.UserRole, int(emp.id))
            self._inclusion_table.setItem(row, 0, flag_item)

            name_item = QTableWidgetItem(emp.employee_display_name or "—")
            self._inclusion_table.setItem(row, 1, name_item)

            net_item = QTableWidgetItem(f"{float(emp.net_payable):,.2f}")
            net_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._inclusion_table.setItem(row, 2, net_item)

            status_label = (emp.status_code or "").capitalize() or "—"
            status_item = QTableWidgetItem(status_label)
            self._inclusion_table.setItem(row, 3, status_item)

            reason_item = QTableWidgetItem(emp.exclusion_reason or "")
            self._inclusion_table.setItem(row, 4, reason_item)

        total = len(self._run_employees)
        excluded = total - included_count
        self._inclusion_summary_label.setText(
            f"<b>{included_count}</b> of {total} employee(s) included; "
            f"<b>{excluded}</b> excluded. Double-click a row or use "
            "<i>Toggle Selected</i> to change status. Excluded employees are "
            "skipped by posting, payments and payslip printing."
        )

    def _on_inclusion_toggle_row(self, row: int, _col: int) -> None:
        self._toggle_inclusion_at_row(row)

    def _on_inclusion_toggle_selected(self) -> None:
        row = self._inclusion_table.currentRow()
        if row < 0:
            self._set_error("Select an employee row first.")
            return
        self._toggle_inclusion_at_row(row)

    def _toggle_inclusion_at_row(self, row: int) -> None:
        if not (0 <= row < len(self._run_employees)):
            return
        emp = self._run_employees[row]
        if (emp.status_code or "").lower() == "error":
            self._set_error(
                "This row has a calculation error. Recalculate the run to "
                "clear it before toggling inclusion."
            )
            return

        currently_included = (emp.status_code or "").lower() == "included"
        if currently_included:
            # Excluding — collect a reason.
            reason, ok = QInputDialog.getText(
                self,
                "Exclude Employee",
                f"Reason for excluding {emp.employee_display_name}:",
                QLineEdit.EchoMode.Normal,
                emp.exclusion_reason or "",
            )
            if not ok:
                return
            reason = reason.strip()
            if not reason:
                self._set_error("A reason is required when excluding an employee.")
                return
            new_included = False
            new_reason: str | None = reason
        else:
            new_included = True
            new_reason = None

        try:
            self._registry.payroll_run_service.set_run_employee_inclusion(
                self._company_id,
                int(emp.id),
                is_included=new_included,
                exclusion_reason=new_reason,
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            self._set_error(f"Could not update inclusion: {exc}")
            return

        self._set_error(None)
        self._refresh_inclusion()

    def _build_approve_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Approve Run")

        self._approve_summary_label = QLabel(card)
        self._approve_summary_label.setObjectName("DialogSectionSummary")
        self._approve_summary_label.setWordWrap(True)
        card.layout().addWidget(self._approve_summary_label)

        self._approve_now_checkbox = QCheckBox(
            "Approve this run now (required before posting)",
            card,
        )
        self._approve_now_checkbox.setChecked(True)
        card.layout().addWidget(self._approve_now_checkbox)

        hint = QLabel(
            "You can defer approval and return later via the "
            "Payroll Runs ribbon. Posting and payslip printing become "
            "available once the run is approved.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Payroll run ready")
        self._done_label = QLabel(card)
        self._done_label.setObjectName("DialogSectionSummary")
        self._done_label.setWordWrap(True)
        card.layout().addWidget(self._done_label)
        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _card(self, title: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("DialogSectionCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        tlabel = QLabel(title, card)
        tlabel.setObjectName("DialogSectionTitle")
        layout.addWidget(tlabel)
        return card

    # ── Buttons ───────────────────────────────────────────────────────

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

        self._apply_button = QPushButton("Finish", self)
        self._apply_button.setProperty("variant", "primary")
        self._apply_button.clicked.connect(self._handle_finish)
        self.button_box.addButton(self._apply_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._close_button = QPushButton("Cancel", self)
        self._close_button.setProperty("variant", "ghost")
        self._close_button.clicked.connect(self.reject)
        self.button_box.addButton(self._close_button, QDialogButtonBox.ButtonRole.RejectRole)

    # ── Defaults / navigation ─────────────────────────────────────────

    def _load_defaults(self) -> None:
        # Default currency from payroll settings if available.
        try:
            settings = self._registry.payroll_setup_service.get_company_payroll_settings(
                self._company_id
            )
        except Exception:  # noqa: BLE001
            settings = None
        default_currency = (
            settings.default_payroll_currency_code if settings else "XAF"
        ) or "XAF"
        self._currency_edit.setText(default_currency)

        today = date.today()
        self._label_edit.setText(f"Payroll {today.year}-{today.month:02d}")

    def _go_next(self) -> None:
        if self._current_step == 0:
            if not self._validate_period():
                return
            self._refresh_readiness()
        elif self._current_step == 1:
            if not self._readiness_passes():
                return
            self._refresh_inputs()
        elif self._current_step == 2:
            # Kick off create+calculate as we move into the Calculate step.
            if not self._run_create_and_calculate():
                return
        elif self._current_step == 3:
            self._refresh_variance()
        elif self._current_step == 4:
            if not self._variance_passes():
                return
            self._refresh_inclusion()
        elif self._current_step == 5:
            self._refresh_approve_summary()
        elif self._current_step == 6:
            self._handle_finish()
            return
        self._current_step += 1
        self._stack.setCurrentIndex(self._current_step)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _go_back(self) -> None:
        if self._current_step <= 0:
            return
        # Once the run has been created, block going back past the
        # Calculate step — the run is already persisted.
        if self._created_run is not None and self._current_step == 4:
            self._set_error(
                "The run has been created. Use Cancel to close the wizard; "
                "the run remains available on the Payroll Runs tab."
            )
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
        on_approve = self._current_step == 6
        on_done = self._current_step == 7
        self._back_button.setVisible(0 < self._current_step and not on_done)
        # Prevent going back past the Calculate step once the run exists.
        self._back_button.setEnabled(
            self._current_step > 0
            and not on_done
            and not (self._created_run is not None and self._current_step == 4)
        )
        self._next_button.setVisible(not on_approve and not on_done)
        self._apply_button.setVisible(on_approve)
        self._close_button.setText("Close" if on_done else "Cancel")

    # ── Step: Period validation ───────────────────────────────────────

    def _validate_period(self) -> bool:
        if not self._label_edit.text().strip():
            self._set_error("Run label is required.")
            return False
        if not self._currency_edit.text().strip():
            self._set_error("Currency is required.")
            return False
        return True

    # ── Step: Readiness ───────────────────────────────────────────────

    def _refresh_readiness(self) -> None:
        try:
            result = self._registry.payroll_validation_service.validate_for_period(
                self._company_id,
                int(self._period_year_spin.value()),
                int(self._period_month_spin.value()),
            )
        except (ValidationError, NotFoundError, PermissionDeniedError) as exc:
            self._validation_result = None
            self._readiness_summary_label.setText(f"Readiness scan failed: {exc}")
            self._issues_table.setRowCount(0)
            return

        self._validation_result = result
        header = (
            f"Employees in scope: <b>{result.employee_count}</b> "
            f"· Errors: <b>{result.error_count}</b> "
            f"· Warnings: <b>{result.warning_count}</b>"
        )
        self._readiness_summary_label.setText(header)

        self._issues_table.setRowCount(len(result.issues))
        for row, issue in enumerate(result.issues):
            sev_item = QTableWidgetItem((issue.severity or "").title())
            emp_item = QTableWidgetItem(issue.employee_display_name or "")
            msg_item = QTableWidgetItem(issue.issue_message or issue.issue_code or "")
            if (issue.severity or "").lower() == "error":
                sev_item.setData(Qt.ItemDataRole.ForegroundRole, None)
                sev_item.setText("Error")
            self._issues_table.setItem(row, 0, sev_item)
            self._issues_table.setItem(row, 1, emp_item)
            self._issues_table.setItem(row, 2, msg_item)

        if result.warning_count > 0 and not result.has_errors:
            self._readiness_acknowledge.show()
            self._readiness_acknowledge.setChecked(False)
        else:
            self._readiness_acknowledge.hide()
            self._readiness_acknowledge.setChecked(False)

    def _readiness_passes(self) -> bool:
        result = self._validation_result
        if result is None:
            self._set_error("Readiness scan did not complete. Go back and try again.")
            return False
        if result.has_errors:
            self._set_error(
                "Blocking errors must be resolved before calculating a run."
            )
            return False
        if result.warning_count > 0 and not self._readiness_acknowledge.isChecked():
            self._set_error("Acknowledge the warnings to continue.")
            return False
        if result.employee_count <= 0:
            self._set_error(
                "No employees are in scope for this period."
            )
            return False
        return True

    # ── Step: Inputs preview ──────────────────────────────────────────

    def _refresh_inputs(self) -> None:
        try:
            batches = self._registry.payroll_input_service.list_batches(
                self._company_id,
                period_year=int(self._period_year_spin.value()),
                period_month=int(self._period_month_spin.value()),
            )
        except Exception:  # noqa: BLE001
            batches = []
        approved = [b for b in batches if (getattr(b, "status_code", "") or "").lower() == "approved"]
        self._input_batches = approved

        if approved:
            self._inputs_hint_label.setText(
                f"<b>{len(approved)}</b> approved batch(es) will be included in the "
                "calculation. Draft or voided batches are ignored."
            )
        else:
            self._inputs_hint_label.setText(
                "No approved variable-input batches for this period. "
                "The run will calculate with recurring components only."
            )

        self._inputs_table.setRowCount(len(approved))
        for row, batch in enumerate(approved):
            reference = getattr(batch, "batch_reference", "") or getattr(batch, "reference", "")
            label = getattr(batch, "batch_label", "") or getattr(batch, "label", "")
            status = (getattr(batch, "status_code", "") or "").title()
            lines = getattr(batch, "line_count", None)
            if lines is None:
                lines = getattr(batch, "lines_count", 0) or 0
            self._inputs_table.setItem(row, 0, QTableWidgetItem(str(reference)))
            self._inputs_table.setItem(row, 1, QTableWidgetItem(str(label)))
            self._inputs_table.setItem(row, 2, QTableWidgetItem(status))
            self._inputs_table.setItem(row, 3, QTableWidgetItem(str(lines)))

    # ── Step: Create + calculate ──────────────────────────────────────

    def _run_create_and_calculate(self) -> bool:
        if self._calculated_run is not None:
            # Already done — allow moving forward.
            return True
        cmd = CreatePayrollRunCommand(
            period_year=int(self._period_year_spin.value()),
            period_month=int(self._period_month_spin.value()),
            run_label=self._label_edit.text().strip(),
            currency_code=self._currency_edit.text().strip(),
            run_date=self._run_date_edit.date().toPython(),
            payment_date=self._payment_date_edit.date().toPython(),
        )
        try:
            created = self._registry.payroll_run_service.create_run(self._company_id, cmd)
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
            self._set_error(f"Create run: {exc}")
            return False
        self._created_run = created
        try:
            calculated = self._registry.payroll_run_service.calculate_run(
                self._company_id, created.id
            )
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
            self._set_error(f"Calculate run: {exc}")
            # Leave the draft run in place; user can cancel and void manually.
            return False
        self._calculated_run = calculated
        try:
            self._run_employees = self._registry.payroll_run_service.list_run_employees(
                self._company_id, created.id
            )
        except Exception:  # noqa: BLE001
            self._run_employees = []
        self._refresh_totals_and_employees()
        return True

    def _refresh_totals_and_employees(self) -> None:
        total_gross = sum(float(e.gross_earnings) for e in self._run_employees)
        total_ded = sum(float(e.total_employee_deductions) for e in self._run_employees)
        total_tax = sum(float(e.total_taxes) for e in self._run_employees)
        total_net = sum(float(e.net_payable) for e in self._run_employees)
        error_count = sum(
            1 for e in self._run_employees if (e.status_code or "").lower() == "error"
        )

        currency = self._currency_edit.text().strip()
        ref = self._calculated_run.run_reference if self._calculated_run else ""
        lines = [
            f"<b>Run</b>: {ref} "
            f"(status {self._calculated_run.status_code if self._calculated_run else '?'})",
            (
                f"<b>Employees</b>: {len(self._run_employees)} "
                f"· <b>Errors</b>: {error_count}"
            ),
            (
                f"<b>Gross</b>: {total_gross:,.2f} {currency} · "
                f"<b>Deductions</b>: {total_ded:,.2f} · "
                f"<b>Taxes</b>: {total_tax:,.2f} · "
                f"<b>Net</b>: {total_net:,.2f}"
            ),
        ]
        self._totals_label.setText("<br>".join(lines))

        self._employees_table.setRowCount(len(self._run_employees))
        for row, emp in enumerate(self._run_employees):
            name_item = QTableWidgetItem(
                f"{emp.employee_number} — {emp.employee_display_name}"
            )
            if (emp.status_code or "").lower() == "error":
                name_item.setText(f"⚠ {emp.employee_number} — {emp.employee_display_name}")
            self._employees_table.setItem(row, 0, name_item)
            for col, value in enumerate(
                (
                    emp.gross_earnings,
                    emp.total_employee_deductions,
                    emp.total_taxes,
                    emp.net_payable,
                ),
                start=1,
            ):
                item = QTableWidgetItem(f"{float(value):,.2f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._employees_table.setItem(row, col, item)

    # ── Step: Variance review ─────────────────────────────────────────

    def _refresh_variance(self) -> None:
        current_by_name = {
            (e.employee_display_name or "").strip(): float(e.net_payable)
            for e in self._run_employees
        }
        # Find a prior period run in the same company. Walk back at most
        # 12 months to find one with calculated/approved/posted status.
        prior_net_by_name: dict[str, float] = {}
        prior_ref: str | None = None
        try:
            all_runs = self._registry.payroll_run_service.list_runs(self._company_id)
        except Exception:  # noqa: BLE001
            all_runs = []
        cur_year = int(self._period_year_spin.value())
        cur_month = int(self._period_month_spin.value())
        cur_key = (cur_year, cur_month)
        candidates = [
            r for r in all_runs
            if (r.period_year, r.period_month) < cur_key
            and (r.status_code or "").lower() in ("calculated", "approved", "posted")
        ]
        candidates.sort(key=lambda r: (r.period_year, r.period_month), reverse=True)
        if candidates:
            prior = candidates[0]
            prior_ref = f"{prior.period_year}-{prior.period_month:02d} ({prior.run_reference})"
            try:
                prior_employees = self._registry.payroll_run_service.list_run_employees(
                    self._company_id, prior.id
                )
            except Exception:  # noqa: BLE001
                prior_employees = []
            for e in prior_employees:
                prior_net_by_name[(e.employee_display_name or "").strip()] = float(e.net_payable)

        # Build rows for every employee in current run + any in prior not in current.
        names = sorted(set(current_by_name) | set(prior_net_by_name))
        self._variance_table.setRowCount(len(names))
        anomaly_count = 0
        currency = self._currency_edit.text().strip()
        for row, name in enumerate(names):
            prior_val = prior_net_by_name.get(name, 0.0)
            curr_val = current_by_name.get(name, 0.0)
            delta = curr_val - prior_val
            pct = (delta / prior_val * 100.0) if prior_val else (100.0 if curr_val else 0.0)
            is_anomaly = abs(pct) > 10.0 if prior_val else bool(curr_val and not prior_val)
            if is_anomaly:
                anomaly_count += 1

            self._variance_table.setItem(row, 0, QTableWidgetItem(name or "—"))
            for col, val, fmt in (
                (1, prior_val, f"{prior_val:,.2f}"),
                (2, curr_val, f"{curr_val:,.2f}"),
                (3, delta, f"{delta:+,.2f}"),
                (4, pct, (f"{pct:+.1f}%" if prior_val or curr_val else "—")),
            ):
                item = QTableWidgetItem(fmt)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if is_anomaly and col == 4:
                    item.setData(Qt.ItemDataRole.ToolTipRole, "Exceeds ±10% vs prior period")
                self._variance_table.setItem(row, col, item)

        if prior_ref is None:
            self._variance_summary_label.setText(
                "No prior calculated run found — this appears to be the first "
                "payroll for this company. Continue to approve."
            )
            self._variance_ack.hide()
            self._variance_ack.setChecked(False)
        else:
            self._variance_summary_label.setText(
                f"Comparing against <b>{prior_ref}</b>. "
                f"<b>{anomaly_count}</b> employee(s) changed by more than ±10% vs prior period "
                f"(currency: {currency})."
            )
            if anomaly_count > 0:
                self._variance_ack.show()
                self._variance_ack.setChecked(False)
            else:
                self._variance_ack.hide()
                self._variance_ack.setChecked(False)

    def _variance_passes(self) -> bool:
        if self._variance_ack.isVisible() and not self._variance_ack.isChecked():
            self._set_error(
                "Acknowledge the variance anomalies (>10% change) to continue."
            )
            return False
        return True

    # ── Step: Approve summary ─────────────────────────────────────────

    def _refresh_approve_summary(self) -> None:
        if self._calculated_run is None:
            self._approve_summary_label.setText("No calculated run.")
            return
        included = [
            e for e in self._run_employees
            if (e.status_code or "").lower() == "included"
        ]
        excluded_count = len(self._run_employees) - len(included)
        total_net = sum(float(e.net_payable) for e in included)
        currency = self._currency_edit.text().strip()
        excluded_suffix = (
            f"<br><b>Excluded</b>: {excluded_count} (not posted, not paid)"
            if excluded_count else ""
        )
        self._approve_summary_label.setText(
            f"<b>Run</b>: {self._calculated_run.run_reference} "
            f"(status {self._calculated_run.status_code})<br>"
            f"<b>Included employees</b>: {len(included)}<br>"
            f"<b>Total Net (included)</b>: {total_net:,.2f} {currency}"
            f"{excluded_suffix}"
        )

    # ── Finish ────────────────────────────────────────────────────────

    def _handle_finish(self) -> None:
        self._set_error(None)
        if self._calculated_run is None:
            self._set_error("No calculated run to finish.")
            return
        run = self._calculated_run
        final_status = run.status_code
        if self._approve_now_checkbox.isChecked():
            self._apply_button.setEnabled(False)
            try:
                self._registry.payroll_run_service.approve_run(self._company_id, run.id)
                self._approved = True
                final_status = "approved"
            except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
                self._set_error(f"Approve: {exc}")
                self._apply_button.setEnabled(True)
                return
            finally:
                self._apply_button.setEnabled(True)

        included = [
            e for e in self._run_employees
            if (e.status_code or "").lower() == "included"
        ]
        excluded_count = len(self._run_employees) - len(included)
        total_gross = sum(float(e.gross_earnings) for e in included)
        total_net = sum(float(e.net_payable) for e in included)

        if self._approved:
            summary = (
                f"Run {run.run_reference} approved. Ready for posting to GL and "
                "payslip printing."
            )
        else:
            summary = (
                f"Run {run.run_reference} calculated (approval deferred). "
                "Return via the Payroll Runs tab to approve when ready."
            )

        self._result = PayrollRunWizardResult(
            run_id=run.id,
            run_reference=run.run_reference,
            period_year=run.period_year,
            period_month=run.period_month,
            status_code=final_status,
            employee_count=len(included),
            total_gross=total_gross,
            total_net=total_net,
            approved=self._approved,
            summary=summary,
        )
        if excluded_count:
            summary += f" {excluded_count} employee(s) excluded."
        self._done_label.setText(summary)
        self._current_step = 7
        self._stack.setCurrentIndex(self._current_step)
        self._update_step_pills()
        self._update_buttons()

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_error(self, message: str | None) -> None:
        if not message:
            self._error_label.clear()
            self._error_label.hide()
            return
        self._error_label.setText(message)
        self._error_label.show()
