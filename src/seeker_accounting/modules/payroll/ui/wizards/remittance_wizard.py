"""RemittanceWizardDialog — guided statutory remittance batch creation.

Orchestrates the deadline-driven remittance flow for DGI / CNPS / Other
authorities. The expert path (``New Batch`` dialog + manual line edits)
remains available as a fast-path alternative on the same ribbon.

Steps:

1. **Authority & Period** — pick authority and period window; show the
   computed statutory filing deadline.
2. **Posted Runs**        — list posted payroll runs overlapping the
   period; operator selects zero or more to seed supporting lines.
3. **Lines & Amount**     — per selected run, the operator enters the
   line amount due for that authority. A blank manual line can also be
   added.
4. **Review & Create**    — show summary (authority, period, deadline,
   total, line count), optional notes, then create the batch + lines.

First-cut scope notes:

- There is no component-to-authority mapping in the current data
  model, so we cannot auto-compute amounts per authority from run
  lines. The operator enters amounts manually. When that mapping
  exists, step 3 can be upgraded to auto-seed.
- ``payroll_remittance_service.create_batch`` requires linked runs to
  be *posted*; the wizard filters the runs list accordingly.
- ``add_line`` does not update ``batch.amount_due``; we pre-compute
  the total from user-entered line amounts and pass it on creation.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_remittance_dto import (
    CreatePayrollRemittanceBatchCommand,
    CreatePayrollRemittanceLineCommand,
)
from seeker_accounting.modules.payroll.services.payroll_remittance_deadline_service import (
    compute_filing_deadline,
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


_AUTHORITY_CHOICES = (
    ("dgi", "DGI — Direction Générale des Impôts"),
    ("cnps", "CNPS — Caisse Nationale de Prévoyance Sociale"),
    ("other", "Other"),
)


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


@dataclass(frozen=True, slots=True)
class _ProposedLine:
    """Internal row — one per selected posted run plus optional manual lines."""
    run_id: int | None
    description: str
    amount_due: Decimal


@dataclass(frozen=True, slots=True)
class RemittanceWizardResult:
    batch_id: int
    batch_number: str
    authority_code: str
    period_start: date
    period_end: date
    amount_due: Decimal
    line_count: int
    filing_deadline: date | None
    linked_run_ids: tuple[int, ...] = field(default_factory=tuple)
    summary: str = ""


class RemittanceWizardDialog(BaseDialog):
    """4-step guided remittance batch wizard — see module docstring."""

    _STEP_LABELS = (
        "1. Authority & Period",
        "2. Posted Runs",
        "3. Lines & Amount",
        "4. Review & Create",
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

        self._posted_runs: list = []
        self._run_checkboxes: dict[int, QCheckBox] = {}
        self._selected_run_ids: list[int] = []
        self._proposed_lines: list[_ProposedLine] = []
        self._created_batch = None
        self._result: RemittanceWizardResult | None = None
        self._current_step = 0

        super().__init__(
            "Remittance Wizard",
            parent,
            help_key="wizard.remittance",
        )
        self.setObjectName("RemittanceWizardDialog")
        self.resize(900, 680)

        intro = QLabel(
            "Create a statutory remittance batch from posted payroll runs. "
            "The wizard computes the filing deadline and lets you seed "
            "supporting lines from the selected runs.",
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
    def result_payload(self) -> RemittanceWizardResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> RemittanceWizardResult | None:
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
        self._stack.addWidget(self._build_runs_page())
        self._stack.addWidget(self._build_lines_page())
        self._stack.addWidget(self._build_review_page())
        self._stack.addWidget(self._build_done_page())
        return self._stack

    def _build_period_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Authority & Period")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self._authority_combo = QComboBox(card)
        for code, label in _AUTHORITY_CHOICES:
            self._authority_combo.addItem(label, code)
        self._authority_combo.currentIndexChanged.connect(self._update_deadline_label)
        grid.addWidget(create_field_block("Authority *", self._authority_combo), 0, 0, 1, 2)

        self._period_start_edit = QDateEdit(card)
        self._period_start_edit.setCalendarPopup(True)
        self._period_start_edit.setDisplayFormat("yyyy-MM-dd")
        self._period_start_edit.dateChanged.connect(self._update_deadline_label)
        grid.addWidget(create_field_block("Period Start *", self._period_start_edit), 1, 0)

        self._period_end_edit = QDateEdit(card)
        self._period_end_edit.setCalendarPopup(True)
        self._period_end_edit.setDisplayFormat("yyyy-MM-dd")
        self._period_end_edit.dateChanged.connect(self._update_deadline_label)
        grid.addWidget(create_field_block("Period End *", self._period_end_edit), 1, 1)

        card.layout().addLayout(grid)

        self._deadline_label = QLabel(card)
        self._deadline_label.setObjectName("DialogSectionSummary")
        self._deadline_label.setWordWrap(True)
        card.layout().addWidget(self._deadline_label)

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_runs_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Posted Payroll Runs in Period")

        hint = QLabel(
            "Select the posted runs whose remittance obligations this batch "
            "covers. Selection is optional — a batch can be created without "
            "linking runs.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._runs_table = QTableWidget(0, 6, card)
        self._runs_table.setHorizontalHeaderLabels(
            ["", "Run #", "Label", "Period", "Employees", "Gross"]
        )
        self._runs_table.verticalHeader().setVisible(False)
        self._runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._runs_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hdr = self._runs_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        card.layout().addWidget(self._runs_table, 1)

        self._no_runs_label = QLabel(
            "<i>No posted runs overlap the selected period.</i>",
            card,
        )
        self._no_runs_label.setObjectName("DialogSectionSummary")
        self._no_runs_label.hide()
        card.layout().addWidget(self._no_runs_label)

        outer.addWidget(card, 1)
        return page

    def _build_lines_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Proposed Lines")

        hint = QLabel(
            "One line per selected run. Enter the remittance amount due to "
            "this authority for each run. Lines with a zero amount will be "
            "skipped. Use the Manual Line field below to add an extra "
            "supporting line not tied to a specific run.",
            card,
        )
        hint.setObjectName("DialogSectionSummary")
        hint.setWordWrap(True)
        card.layout().addWidget(hint)

        self._lines_table = QTableWidget(0, 3, card)
        self._lines_table.setHorizontalHeaderLabels(
            ["Source Run", "Description", "Amount Due"]
        )
        self._lines_table.verticalHeader().setVisible(False)
        hdr = self._lines_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._lines_table.setEditTriggers(
            QAbstractItemView.EditTrigger.AllEditTriggers
        )
        card.layout().addWidget(self._lines_table, 1)

        # Manual line entry
        manual_frame = QFrame(card)
        manual_layout = QGridLayout(manual_frame)
        manual_layout.setContentsMargins(0, 8, 0, 0)
        manual_layout.setHorizontalSpacing(12)

        self._manual_desc_edit = QLineEdit(manual_frame)
        self._manual_desc_edit.setPlaceholderText("Manual line description (optional)")
        manual_layout.addWidget(
            create_field_block("Manual Line Description", self._manual_desc_edit),
            0, 0,
        )

        self._manual_amount_edit = QLineEdit(manual_frame)
        self._manual_amount_edit.setPlaceholderText("0.00")
        manual_layout.addWidget(
            create_field_block("Manual Line Amount", self._manual_amount_edit),
            0, 1,
        )
        card.layout().addWidget(manual_frame)

        self._total_label = QLabel(card)
        self._total_label.setObjectName("DialogSectionSummary")
        card.layout().addWidget(self._total_label)

        outer.addWidget(card, 1)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Review & Create")

        self._review_label = QLabel(card)
        self._review_label.setObjectName("DialogSectionSummary")
        self._review_label.setWordWrap(True)
        card.layout().addWidget(self._review_label)

        self._notes_edit = QPlainTextEdit(card)
        self._notes_edit.setPlaceholderText("Optional batch-level notes.")
        self._notes_edit.setFixedHeight(80)
        card.layout().addWidget(create_field_block("Notes", self._notes_edit))

        outer.addWidget(card)
        outer.addStretch(1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        card = self._card("Remittance Batch Created")
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

        self._apply_button = QPushButton("Create Batch", self)
        self._apply_button.setProperty("variant", "primary")
        self._apply_button.clicked.connect(self._handle_apply)
        self.button_box.addButton(self._apply_button, QDialogButtonBox.ButtonRole.ActionRole)

        self._close_button = QPushButton("Cancel", self)
        self._close_button.setProperty("variant", "ghost")
        self._close_button.clicked.connect(self.reject)
        self.button_box.addButton(self._close_button, QDialogButtonBox.ButtonRole.RejectRole)

    # ── Defaults ──────────────────────────────────────────────────────

    def _load_defaults(self) -> None:
        today = date.today()
        # Default to previous month (remittances typically filed after a
        # period ends).
        if today.month == 1:
            start = date(today.year - 1, 12, 1)
            end = date(today.year - 1, 12, 31)
        else:
            prev_month = today.month - 1
            start = date(today.year, prev_month, 1)
            end = date(today.year, prev_month, _last_day(today.year, prev_month))
        self._period_start_edit.setDate(QDate(start.year, start.month, start.day))
        self._period_end_edit.setDate(QDate(end.year, end.month, end.day))
        self._update_deadline_label()

    def _update_deadline_label(self) -> None:
        auth = self._authority_combo.currentData()
        period_end = self._period_end_edit.date().toPython()
        deadline = compute_filing_deadline(auth, period_end)
        if deadline is None:
            self._deadline_label.setText(
                "<i>No statutory filing deadline for this authority.</i>"
            )
        else:
            days = (deadline - date.today()).days
            if days < 0:
                self._deadline_label.setText(
                    f"<b>Filing deadline:</b> {deadline.isoformat()} "
                    f"<span style='color:#c62828;'>(overdue by {-days} days)</span>"
                )
            else:
                self._deadline_label.setText(
                    f"<b>Filing deadline:</b> {deadline.isoformat()} "
                    f"({days} days from today)"
                )

    # ── Step 2: load posted runs ──────────────────────────────────────

    def _load_posted_runs(self) -> None:
        try:
            all_runs = self._registry.payroll_run_service.list_runs(
                self._company_id, status_code="posted"
            )
        except Exception:  # noqa: BLE001
            _log.warning("Posted run load error", exc_info=True)
            all_runs = []

        ps = self._period_start_edit.date().toPython()
        pe = self._period_end_edit.date().toPython()

        def _run_period_end(r) -> date:
            year = r.period_year
            month = r.period_month
            if not year or not month:
                return date.max
            return date(year, month, _last_day(year, month))

        def _run_period_start(r) -> date:
            year = r.period_year
            month = r.period_month
            if not year or not month:
                return date.min
            return date(year, month, 1)

        # Overlap test: run period intersects wizard period.
        overlapping = [
            r for r in all_runs
            if _run_period_start(r) <= pe and _run_period_end(r) >= ps
        ]
        self._posted_runs = overlapping

        self._runs_table.setRowCount(0)
        self._run_checkboxes: dict[int, QCheckBox] = {}
        for r in overlapping:
            ri = self._runs_table.rowCount()
            self._runs_table.insertRow(ri)
            cb = QCheckBox()
            cb.setChecked(True)
            self._runs_table.setCellWidget(ri, 0, cb)
            self._run_checkboxes[r.id] = cb
            self._runs_table.setItem(ri, 1, QTableWidgetItem(r.run_reference or ""))
            self._runs_table.setItem(ri, 2, QTableWidgetItem(r.run_label or ""))
            period_text = f"{r.period_year}-{r.period_month:02d}" if r.period_year else "—"
            self._runs_table.setItem(ri, 3, QTableWidgetItem(period_text))
            self._runs_table.setItem(
                ri, 4, QTableWidgetItem(str(r.employee_count or 0))
            )
            self._runs_table.setItem(
                ri, 5,
                QTableWidgetItem(
                    f"{Decimal(str(r.total_gross_earnings or 0)):,.2f}"
                ),
            )
        self._no_runs_label.setVisible(not overlapping)
        self._runs_table.setVisible(bool(overlapping))

    def _collect_selected_runs(self) -> list:
        return [r for r in self._posted_runs if self._run_checkboxes.get(r.id) and self._run_checkboxes[r.id].isChecked()]

    # ── Step 3: lines ─────────────────────────────────────────────────

    def _refresh_lines_page(self) -> None:
        selected = self._collect_selected_runs()
        auth_label = self._authority_combo.currentText().split(" — ")[0]
        self._lines_table.setRowCount(0)
        self._proposed_lines = []
        for r in selected:
            ri = self._lines_table.rowCount()
            self._lines_table.insertRow(ri)
            src_item = QTableWidgetItem(r.run_reference or "")
            src_item.setFlags(src_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            src_item.setData(Qt.ItemDataRole.UserRole, r.id)
            self._lines_table.setItem(ri, 0, src_item)
            desc = f"{auth_label} — {r.run_reference or ''}".strip(" —")
            self._lines_table.setItem(ri, 1, QTableWidgetItem(desc))
            self._lines_table.setItem(ri, 2, QTableWidgetItem("0.00"))
        self._lines_table.itemChanged.connect(self._recompute_total)
        self._manual_amount_edit.textChanged.connect(self._recompute_total)
        self._manual_desc_edit.textChanged.connect(self._recompute_total)
        self._recompute_total()

    def _collect_line_rows(self) -> tuple[list[_ProposedLine], Decimal, str | None]:
        """Return (lines, total, error_message)."""
        lines: list[_ProposedLine] = []
        total = Decimal("0")
        for row in range(self._lines_table.rowCount()):
            src_item = self._lines_table.item(row, 0)
            desc_item = self._lines_table.item(row, 1)
            amt_item = self._lines_table.item(row, 2)
            run_id = src_item.data(Qt.ItemDataRole.UserRole) if src_item else None
            desc = (desc_item.text() if desc_item else "").strip()
            amt_text = (amt_item.text() if amt_item else "").strip() or "0"
            try:
                amount = Decimal(amt_text)
            except InvalidOperation:
                return [], Decimal("0"), f"Row {row + 1}: amount is not a number."
            if amount < 0:
                return [], Decimal("0"), f"Row {row + 1}: amount cannot be negative."
            if amount == 0:
                continue  # skip zero lines
            if not desc:
                return [], Decimal("0"), f"Row {row + 1}: description is required."
            lines.append(
                _ProposedLine(
                    run_id=int(run_id) if isinstance(run_id, int) else None,
                    description=desc,
                    amount_due=amount,
                )
            )
            total += amount

        manual_desc = self._manual_desc_edit.text().strip()
        manual_amt_text = self._manual_amount_edit.text().strip()
        if manual_desc or manual_amt_text:
            if not manual_desc:
                return [], Decimal("0"), "Manual line: description is required."
            if not manual_amt_text:
                return [], Decimal("0"), "Manual line: amount is required."
            try:
                manual_amount = Decimal(manual_amt_text)
            except InvalidOperation:
                return [], Decimal("0"), "Manual line: amount is not a number."
            if manual_amount <= 0:
                return [], Decimal("0"), "Manual line: amount must be greater than zero."
            lines.append(
                _ProposedLine(
                    run_id=None,
                    description=manual_desc,
                    amount_due=manual_amount,
                )
            )
            total += manual_amount

        return lines, total, None

    def _recompute_total(self, *_args) -> None:
        lines, total, err = self._collect_line_rows()
        if err:
            self._total_label.setText(f"<b>Total:</b> — ({err})")
        else:
            self._total_label.setText(
                f"<b>Total:</b> {total:,.2f}  ·  {len(lines)} line(s)"
            )

    # ── Navigation ────────────────────────────────────────────────────

    def _go_next(self) -> None:
        if self._current_step == 0 and not self._validate_period():
            return
        if self._current_step == 3:  # review → apply
            self._handle_apply()
            return

        self._current_step += 1
        if self._current_step == 1:
            self._load_posted_runs()
        elif self._current_step == 2:
            self._refresh_lines_page()
        elif self._current_step == 3:
            self._refresh_review()
        self._stack.setCurrentIndex(self._current_step)
        self._set_error(None)
        self._update_step_pills()
        self._update_buttons()

    def _go_back(self) -> None:
        if self._current_step <= 0:
            return
        if self._created_batch is not None:
            self._set_error(
                "Batch already created — use Cancel to close; it is visible "
                "on the Remittances tab."
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
        on_review = self._current_step == 3
        on_done = self._current_step == 4
        self._back_button.setVisible(self._current_step > 0 and not on_done)
        self._next_button.setVisible(not on_review and not on_done)
        self._apply_button.setVisible(on_review)
        self._close_button.setText("Close" if on_done else "Cancel")

    def _set_error(self, msg: str | None) -> None:
        if not msg:
            self._error_label.hide()
            self._error_label.clear()
            return
        self._error_label.setText(msg)
        self._error_label.show()

    # ── Validation ────────────────────────────────────────────────────

    def _validate_period(self) -> bool:
        ps = self._period_start_edit.date().toPython()
        pe = self._period_end_edit.date().toPython()
        if ps > pe:
            self._set_error("Period start must not be after period end.")
            return False
        if self._authority_combo.currentData() is None:
            self._set_error("Select an authority.")
            return False
        return True

    # ── Review ────────────────────────────────────────────────────────

    def _refresh_review(self) -> None:
        lines, total, err = self._collect_line_rows()
        auth_code = self._authority_combo.currentData()
        auth_label = self._authority_combo.currentText()
        ps = self._period_start_edit.date().toPython()
        pe = self._period_end_edit.date().toPython()
        deadline = compute_filing_deadline(auth_code, pe)
        deadline_text = deadline.isoformat() if deadline else "—"
        linked_runs = sorted({ln.run_id for ln in lines if ln.run_id is not None})
        issue = f"<br><span style='color:#c62828;'><b>Cannot create:</b> {err}</span>" if err else ""
        self._review_label.setText(
            f"<b>Authority:</b> {auth_label}<br>"
            f"<b>Period:</b> {ps.isoformat()} → {pe.isoformat()}<br>"
            f"<b>Filing deadline:</b> {deadline_text}<br>"
            f"<b>Line count:</b> {len(lines)}<br>"
            f"<b>Linked posted runs:</b> "
            f"{', '.join(str(rid) for rid in linked_runs) or '—'}<br>"
            f"<b>Total amount due:</b> {total:,.2f}"
            f"{issue}"
        )

    # ── Apply ─────────────────────────────────────────────────────────

    def _handle_apply(self) -> None:
        lines, total, err = self._collect_line_rows()
        if err:
            self._set_error(err)
            return
        if not lines:
            self._set_error(
                "At least one line with a non-zero amount is required."
            )
            return

        auth_code = self._authority_combo.currentData()
        ps = self._period_start_edit.date().toPython()
        pe = self._period_end_edit.date().toPython()
        notes = self._notes_edit.toPlainText().strip() or None
        # Link the first selected run to the batch (service allows one).
        linked_run_id = next(
            (ln.run_id for ln in lines if ln.run_id is not None), None
        )

        svc = self._registry.payroll_remittance_service
        try:
            batch = svc.create_batch(
                self._company_id,
                CreatePayrollRemittanceBatchCommand(
                    period_start_date=ps,
                    period_end_date=pe,
                    remittance_authority_code=auth_code,
                    payroll_run_id=linked_run_id,
                    amount_due=total,
                    notes=notes,
                ),
            )
        except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
            self._set_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            _log.exception("Remittance batch create failed")
            self._set_error(f"Unexpected error: {exc}")
            return

        self._created_batch = batch
        line_errors: list[str] = []
        for ln in lines:
            try:
                svc.add_line(
                    self._company_id, batch.id,
                    CreatePayrollRemittanceLineCommand(
                        description=ln.description,
                        amount_due=ln.amount_due,
                    ),
                )
            except (ValidationError, ConflictError, NotFoundError, PermissionDeniedError) as exc:
                line_errors.append(f"{ln.description}: {exc}")

        deadline = compute_filing_deadline(auth_code, pe)
        summary = (
            f"Remittance batch {batch.batch_number} created.\n"
            f"Authority: {self._authority_combo.currentText()}\n"
            f"Period: {ps.isoformat()} → {pe.isoformat()}\n"
            f"Total due: {total:,.2f}  ·  {len(lines)} line(s)\n"
            f"Filing deadline: {deadline.isoformat() if deadline else '—'}"
        )
        if line_errors:
            summary += "\n\nWarnings:\n" + "\n".join(f"- {e}" for e in line_errors)

        self._result = RemittanceWizardResult(
            batch_id=batch.id,
            batch_number=batch.batch_number,
            authority_code=auth_code,
            period_start=ps,
            period_end=pe,
            amount_due=total,
            line_count=len(lines) - len(line_errors),
            filing_deadline=deadline,
            linked_run_ids=tuple(sorted({ln.run_id for ln in lines if ln.run_id is not None})),
            summary=summary,
        )

        self._done_label.setText(summary.replace("\n", "<br>"))
        self._current_step = 4
        self._stack.setCurrentIndex(4)
        self._update_step_pills()
        self._update_buttons()
