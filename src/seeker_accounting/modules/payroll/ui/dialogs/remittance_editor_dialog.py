"""RemittanceEditorDialog — single-page statutory remittance batch editor.

P5.S4 replacement for the legacy 4-step ``remittance_wizard`` module.

Single-page workflow:

* Header strip with **Authority** picker (loaded from the registry; falls
  back to legacy DGI/CNPS/Other codes if no authorities have been
  registered yet) and **Period** picker (year + month).
* Filing-deadline banner with overdue / due-soon emphasis based on the
  authority's ``filing_cadence_code`` + ``deadline_day``.
* "Recompute lines" button drives :class:`PayrollRemittanceEngine`; the
  resulting estimate (per-component amounts × mapping fraction) populates
  an editable line table. Each line shows component, side, line-kind,
  computed amount and an editable override.
* Engine warnings (no mappings, no qualifying runs, multi-currency,
  components without run lines) are surfaced in a dedicated warnings band
  so the operator sees them before committing.
* "Create Batch" creates the remittance batch and seeds one
  ``CreatePayrollRemittanceLineCommand`` per visible line.

The legacy expert dialogs (``PayrollRemittanceBatchDialog`` /
``PayrollRemittanceLineDialog``) remain for ad-hoc additions.
"""
from __future__ import annotations

from seeker_accounting.shared.ui.layout_constraints import apply_window_size
import calendar
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
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
    AppError,
    NotFoundError,
    ValidationError,
)
from seeker_accounting.shared.ui.dialogs import BaseDialog


_log = logging.getLogger(__name__)

# Legacy fallback authorities for companies that have not applied a
# statutory pack yet.  Once authorities exist in the registry, they take
# precedence and this list is hidden.
_LEGACY_AUTHORITY_CHOICES: list[tuple[str, str]] = [
    ("dgi", "DGI — Tax Authority"),
    ("cnps", "CNPS — Social Insurance"),
    ("other", "Other"),
]

_MONTH_NAMES = [
    (1, "January"), (2, "February"), (3, "March"), (4, "April"),
    (5, "May"), (6, "June"), (7, "July"), (8, "August"),
    (9, "September"), (10, "October"), (11, "November"), (12, "December"),
]


@dataclass(slots=True)
class _EditorLine:
    """One editable line, derived from an engine estimate or added blank."""
    component_id: int | None
    component_code: str
    component_name: str
    side: str
    line_kind: str
    description: str
    amount_due: Decimal
    liability_account_id: int | None


@dataclass(frozen=True, slots=True)
class RemittanceEditorResult:
    """Returned from :meth:`RemittanceEditorDialog.run` on successful create."""
    batch_id: int
    batch_number: str
    authority_code: str
    period_start: date
    period_end: date
    line_count: int
    amount_due: Decimal
    summary: str = ""


class RemittanceEditorDialog(BaseDialog):
    """Single-page Remittance editor — replaces the legacy wizard."""

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
        self._lines: list[_EditorLine] = []
        self._authorities: list[Any] = []
        self._result: RemittanceEditorResult | None = None

        super().__init__(
            "Remittance Editor",
            parent,
            help_key="dialog.remittance_editor",
        )
        self.setObjectName("RemittanceEditorDialog")
        apply_window_size(self, "modules.payroll.ui.dialogs.remittance.editor.dialog.0")

        intro = QLabel(
            "Pick an authority and period, then recompute lines from posted "
            "payroll runs. Adjust amounts inline and create the batch.",
            self,
        )
        intro.setWordWrap(True)
        self.body_layout.addWidget(intro)

        company_label = QLabel(f"<b>Company:</b> {company_name}", self)
        company_label.setTextFormat(Qt.TextFormat.RichText)
        self.body_layout.addWidget(company_label)

        self.body_layout.addWidget(self._build_header_strip())
        self.body_layout.addWidget(self._build_deadline_banner())
        self.body_layout.addWidget(self._build_warnings_label())
        self.body_layout.addWidget(self._build_lines_table(), 1)
        self.body_layout.addWidget(self._build_totals_row())
        self.body_layout.addWidget(self._build_notes_field())
        self._install_buttons()

        self._reload_authorities()
        self._refresh_deadline()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def result_payload(self) -> RemittanceEditorResult | None:
        return self._result

    @classmethod
    def run(
        cls,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        parent: QWidget | None = None,
    ) -> RemittanceEditorResult | None:
        dlg = cls(service_registry, company_id, company_name, parent=parent)
        dlg.exec()
        return dlg.result_payload

    # ── Builders ──────────────────────────────────────────────────────

    def _build_header_strip(self) -> QWidget:
        wrap = QFrame(self)
        wrap.setObjectName("RemittanceEditorHeader")
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Statutory authority:", wrap))
        self._authority_combo = QComboBox(wrap)
        self._authority_combo.setMinimumWidth(220)
        self._authority_combo.currentIndexChanged.connect(self._on_authority_changed)
        layout.addWidget(self._authority_combo, 1)

        layout.addSpacing(12)
        layout.addWidget(QLabel("Year:", wrap))
        today = date.today()
        self._year_spin = QSpinBox(wrap)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(today.year)
        self._year_spin.valueChanged.connect(self._refresh_deadline)
        layout.addWidget(self._year_spin)

        layout.addWidget(QLabel("Month:", wrap))
        self._month_combo = QComboBox(wrap)
        for num, name in _MONTH_NAMES:
            self._month_combo.addItem(name, num)
        self._month_combo.setCurrentIndex(today.month - 1)
        self._month_combo.currentIndexChanged.connect(self._refresh_deadline)
        layout.addWidget(self._month_combo)

        layout.addSpacing(12)
        self._btn_recompute = QPushButton("Recompute lines", wrap)
        self._btn_recompute.clicked.connect(self._on_recompute)
        layout.addWidget(self._btn_recompute)

        return wrap

    def _build_deadline_banner(self) -> QWidget:
        self._deadline_label = QLabel("", self)
        self._deadline_label.setObjectName("RemittanceDeadlineBanner")
        self._deadline_label.setWordWrap(True)
        self._deadline_label.setTextFormat(Qt.TextFormat.RichText)
        return self._deadline_label

    def _build_warnings_label(self) -> QWidget:
        self._warnings_label = QLabel("", self)
        self._warnings_label.setObjectName("RemittanceWarningsLabel")
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setTextFormat(Qt.TextFormat.RichText)
        self._warnings_label.hide()
        return self._warnings_label

    def _build_lines_table(self) -> QWidget:
        self._lines_table = QTableWidget(0, 5, self)
        self._lines_table.setHorizontalHeaderLabels([
            "Payroll component", "Side", "Kind", "Description", "Amount Due",
        ])
        self._lines_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._lines_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._lines_table.verticalHeader().setVisible(False)
        header = self._lines_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._lines_table.itemChanged.connect(self._on_line_amount_edited)
        return self._lines_table

    def _build_totals_row(self) -> QWidget:
        wrap = QWidget(self)
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        layout.addWidget(QLabel("<b>Total:</b>", wrap))
        self._total_label = QLabel("0.00", wrap)
        self._total_label.setObjectName("RemittanceTotalLabel")
        layout.addWidget(self._total_label)
        return wrap

    def _build_notes_field(self) -> QWidget:
        wrap = QWidget(self)
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QLabel("Notes (optional):", wrap))
        self._notes = QPlainTextEdit(wrap)
        self._notes.setMaximumHeight(60)
        self._notes.setPlaceholderText("Optional notes for this batch.")
        layout.addWidget(self._notes)
        return wrap

    def _install_buttons(self) -> None:
        # Replace the BaseDialog Close-only button box with Create / Cancel.
        self.button_box.clear()
        self.button_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        create_btn = self.button_box.addButton(
            "Create Batch", QDialogButtonBox.ButtonRole.AcceptRole,
        )
        create_btn.clicked.connect(self._on_create)

    # ── Data loaders ──────────────────────────────────────────────────

    def _reload_authorities(self) -> None:
        """Populate the authority combo from the registry, fall back to legacy."""
        self._authority_combo.blockSignals(True)
        try:
            self._authority_combo.clear()
            try:
                self._authorities = list(
                    self._registry.payroll_authority_service.list_authorities(
                        self._company_id, active_only=True,
                    )
                )
            except Exception:
                _log.warning("Failed to load payroll authorities", exc_info=True)
                self._authorities = []
            if self._authorities:
                for a in self._authorities:
                    self._authority_combo.addItem(f"{a.code} — {a.name}", a)
            else:
                # Legacy fallback — synthesize lightweight dicts so downstream
                # code can treat them uniformly.
                for code, label in _LEGACY_AUTHORITY_CHOICES:
                    self._authority_combo.addItem(label, _LegacyAuthority(code, label))
        finally:
            self._authority_combo.blockSignals(False)

    def _on_authority_changed(self) -> None:
        # Clear lines because they are tied to the previous authority.
        self._lines = []
        self._render_lines()
        self._refresh_deadline()

    # ── Deadline banner ──────────────────────────────────────────────

    def _period_dates(self) -> tuple[date, date]:
        year = self._year_spin.value()
        month = self._month_combo.currentData()
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)

    def _selected_authority_code(self) -> str | None:
        data = self._authority_combo.currentData()
        if data is None:
            return None
        return getattr(data, "code", None)

    def _refresh_deadline(self) -> None:
        code = self._selected_authority_code()
        if not code:
            self._deadline_label.setText("")
            return
        _, period_end = self._period_dates()
        deadline = compute_filing_deadline(code, period_end)
        if deadline is None:
            self._deadline_label.setText(
                f"<i>No filing deadline configured for authority '{code}'.</i>"
            )
            return
        days_left = (deadline - date.today()).days
        if days_left < 0:
            color, suffix = "#b00020", f"overdue by {-days_left} day(s)"
        elif days_left <= 7:
            color, suffix = "#a05a00", f"due in {days_left} day(s)"
        else:
            color, suffix = "#1f7a3a", f"due in {days_left} day(s)"
        self._deadline_label.setText(
            f"<b>Filing deadline:</b> {deadline.isoformat()} "
            f"<span style='color:{color}'>({suffix})</span>"
        )

    # ── Engine integration ───────────────────────────────────────────

    def _on_recompute(self) -> None:
        data = self._authority_combo.currentData()
        if data is None or isinstance(data, _LegacyAuthority):
            self._show_warnings(
                "Authority must be registered (apply a statutory pack) before "
                "lines can be auto-computed. Use the legacy New Batch dialog "
                "for free-form entry."
            )
            return
        authority = data
        period_start, period_end = self._period_dates()
        try:
            estimate = self._registry.payroll_remittance_engine.estimate_for_period(
                self._company_id,
                authority_id=authority.id,
                period_year=period_start.year,
                period_month=period_start.month,
            )
        except (NotFoundError, ValidationError) as exc:
            self._show_warnings(str(exc))
            return
        except Exception:
            _log.exception("Remittance engine failure")
            self._show_warnings(
                "Failed to compute remittance lines. See application log for details."
            )
            return

        self._lines = [
            _EditorLine(
                component_id=line.component_id,
                component_code=line.component_code,
                component_name=line.component_name,
                side=line.side,
                line_kind=line.line_kind,
                description=(
                    f"{line.component_code} — {line.component_name} "
                    f"({line.side})"
                ),
                amount_due=Decimal(line.amount),
                liability_account_id=line.liability_account_id,
            )
            for line in estimate.lines
        ]
        self._render_lines()
        if estimate.warnings:
            self._show_warnings(
                "<br/>".join(f"• {w}" for w in estimate.warnings)
            )
        else:
            self._warnings_label.hide()

    def _show_warnings(self, html: str) -> None:
        self._warnings_label.setText(
            f"<span style='color:#a05a00'>{html}</span>"
        )
        self._warnings_label.show()

    def _render_lines(self) -> None:
        self._lines_table.blockSignals(True)
        try:
            self._lines_table.setRowCount(0)
            for line in self._lines:
                row = self._lines_table.rowCount()
                self._lines_table.insertRow(row)
                comp_item = QTableWidgetItem(
                    f"{line.component_code} — {line.component_name}"
                )
                comp_item.setFlags(comp_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._lines_table.setItem(row, 0, comp_item)

                side_item = QTableWidgetItem(line.side)
                side_item.setFlags(side_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._lines_table.setItem(row, 1, side_item)

                kind_item = QTableWidgetItem(line.line_kind)
                kind_item.setFlags(kind_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._lines_table.setItem(row, 2, kind_item)

                self._lines_table.setItem(row, 3, QTableWidgetItem(line.description))

                amt_item = QTableWidgetItem(f"{line.amount_due:.2f}")
                amt_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self._lines_table.setItem(row, 4, amt_item)
        finally:
            self._lines_table.blockSignals(False)
        self._refresh_total()

    def _on_line_amount_edited(self, item: QTableWidgetItem) -> None:
        if item.column() == 4:
            row = item.row()
            try:
                value = Decimal(item.text().replace(",", "").strip() or "0")
            except (InvalidOperation, ValueError):
                value = self._lines[row].amount_due
                item.setText(f"{value:.2f}")
            self._lines[row].amount_due = value
            self._refresh_total()
        elif item.column() == 3:
            self._lines[item.row()].description = item.text().strip()

    def _refresh_total(self) -> None:
        total = sum((line.amount_due for line in self._lines), start=Decimal("0"))
        self._total_label.setText(f"{total:.2f}")

    # ── Create ────────────────────────────────────────────────────────

    def _on_create(self) -> None:
        data = self._authority_combo.currentData()
        if data is None:
            self._show_warnings("Select an authority before creating a batch.")
            return
        code = data.code
        if not self._lines:
            self._show_warnings(
                "No lines to create. Click 'Recompute Lines' to populate from "
                "posted runs, or use the legacy New Batch dialog for free-form entry."
            )
            return
        period_start, period_end = self._period_dates()
        total = sum((line.amount_due for line in self._lines), start=Decimal("0"))
        notes = self._notes.toPlainText().strip() or None

        svc = self._registry.payroll_remittance_service
        try:
            batch = svc.create_batch(
                self._company_id,
                CreatePayrollRemittanceBatchCommand(
                    period_start_date=period_start,
                    period_end_date=period_end,
                    remittance_authority_code=code,
                    payroll_run_id=None,
                    amount_due=total,
                    notes=notes,
                ),
            )
            for line in self._lines:
                svc.add_line(
                    self._company_id,
                    batch.id,
                    CreatePayrollRemittanceLineCommand(
                        description=line.description or line.component_code,
                        amount_due=line.amount_due,
                        payroll_component_id=line.component_id,
                        liability_account_id=line.liability_account_id,
                    ),
                )
        except AppError as exc:
            self._show_warnings(str(exc))
            return
        except Exception:
            _log.exception("Remittance batch create failed")
            self._show_warnings(
                "Failed to create remittance batch. See application log for details."
            )
            return

        self._result = RemittanceEditorResult(
            batch_id=batch.id,
            batch_number=batch.batch_number,
            authority_code=code,
            period_start=period_start,
            period_end=period_end,
            line_count=len(self._lines),
            amount_due=total,
            summary=(
                f"Created batch {batch.batch_number} for {code} "
                f"({period_start.isoformat()} → {period_end.isoformat()}) "
                f"with {len(self._lines)} line(s), total {total:.2f}."
            ),
        )
        self.accept()


@dataclass(frozen=True, slots=True)
class _LegacyAuthority:
    """Lightweight authority shim used when the registry is empty."""
    code: str
    name: str
