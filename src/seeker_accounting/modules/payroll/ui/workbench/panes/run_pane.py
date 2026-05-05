"""Payroll workbench Run pane (Phase 3, P3.S1 integration).

Lists payroll runs for the active company and provides primary run
lifecycle actions: start a new run and open an existing run in the
cockpit.

Layout
------
* Compact toolbar — "New Run" (primary), "Open Run" (selection-gated).
* DataTable — all runs, most-recent first, with status chip column.

Integration
-----------
* "New Run"      → shows a minimal creation dialog, then opens the cockpit.
* "Open Run"     → opens :class:`PayrollRunCockpitWindow` via
                   ``child_window_manager`` if available.
* Double-click   → same as "Open Run".

Graceful degradation
--------------------
* No active company → toolbar disabled, empty table.
* ``payroll_run_service`` missing → empty table, warn-logged.
* ``child_window_manager`` missing → fallback to window.show().
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreateOffCyclePayrollRunCommand,
    CreatePayrollRunCommand,
    PayrollRunListItemDTO,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn, StatusChip
from seeker_accounting.shared.ui.keyboard_shortcuts import install_shortcut, shortcut_map
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

logger = logging.getLogger(__name__)

# ── Column definitions ────────────────────────────────────────────────────────

_COLUMNS: list[DataTableColumn] = [
    DataTableColumn(key="run_reference", title="Reference", width=120),
    DataTableColumn(key="run_label", title="Label", width=220),
    DataTableColumn(key="period", title="Period", width=110),
    DataTableColumn(key="run_type", title="Type", width=80),
    DataTableColumn(key="status_code", title="Status", width=110),
    DataTableColumn(key="employee_count", title="Employees", width=90, is_numeric=True),
    DataTableColumn(key="total_net_payable", title="Net Payable", width=130, is_numeric=True),
]

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


# ── Table model ───────────────────────────────────────────────────────────────

class _RunTableModel(QAbstractTableModel):
    _HEADERS = ("Reference", "Label", "Period", "Type", "Status", "Employees", "Net Payable")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[PayrollRunListItemDTO] = []

    def load(self, rows: list[PayrollRunListItemDTO]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        # Most-recent first: sort by (year desc, month desc, sequence desc)
        self._rows.sort(
            key=lambda r: (r.period_year, r.period_month, r.run_sequence),
            reverse=True,
        )
        self.endResetModel()

    def row_dto(self, row: int) -> PayrollRunListItemDTO | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N803
        return 0 if parent.isValid() else len(self._HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.run_reference or ""
            if col == 1:
                return row.run_label or ""
            if col == 2:
                month_name = _MONTHS[row.period_month - 1] if 1 <= row.period_month <= 12 else str(row.period_month)
                return f"{month_name} {row.period_year}"
            if col == 3:
                return (row.run_type_code or "regular").replace("_", " ").title()
            if col == 4:
                return (row.status_code or "").replace("_", " ").title()
            if col == 5:
                return str(row.employee_count)
            if col == 6:
                amt = row.total_net_payable
                ccy = row.currency_code or ""
                if amt:
                    return f"{ccy} {amt:,.0f}".strip()
                return "—"

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (5, 6):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._HEADERS)
        ):
            return self._HEADERS[section]
        return None


# ── "New Run" dialog ──────────────────────────────────────────────────────────


_OFF_CYCLE_REASONS: list[tuple[str, str]] = [
    ("bonus",            "Bonus / Incentive"),
    ("termination_pay",  "Termination / Final Pay"),
    ("correction",       "Payroll Correction"),
    ("supplemental",     "Supplemental Payment"),
    ("special_allowance","Special Allowance"),
    ("other",            "Other"),
]

class _NewRunDialog(QDialog):
    """Minimal dialog to collect period + label for a new payroll run."""

    def __init__(
        self,
        company_currency: str = "XAF",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Payroll run")
        self.setMinimumWidth(DEFAULT_TOKENS.sizes.workbench_pane_min_w)

        today = date.today()
        self._year_value = today.year
        self._month_value = today.month
        self._currency_value = company_currency
        self._cmd: CreatePayrollRunCommand | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        # Year
        self._year_spin = QSpinBox(self)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(today.year)
        grid.addWidget(QLabel("Year", self), 0, 0)
        grid.addWidget(self._year_spin, 0, 1)

        # Month
        self._month_combo = QComboBox(self)
        for m in _MONTHS:
            self._month_combo.addItem(m)
        self._month_combo.setCurrentIndex(today.month - 1)
        grid.addWidget(QLabel("Month", self), 1, 0)
        grid.addWidget(self._month_combo, 1, 1)

        # Currency
        self._ccy_combo = QComboBox(self)
        for ccy in ("XAF", "USD", "EUR", "GBP", "XOF"):
            self._ccy_combo.addItem(ccy)
        idx = self._ccy_combo.findText(company_currency)
        if idx >= 0:
            self._ccy_combo.setCurrentIndex(idx)
        grid.addWidget(QLabel("Currency", self), 2, 0)
        grid.addWidget(self._ccy_combo, 2, 1)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        year = self._year_spin.value()
        month = self._month_combo.currentIndex() + 1
        currency = self._ccy_combo.currentText()
        month_name = _MONTHS[month - 1]
        self._cmd = CreatePayrollRunCommand(
            period_year=year,
            period_month=month,
            run_label=f"{month_name} {year} Payroll",
            currency_code=currency,
            run_date=date.today(),
        )
        self.accept()

    @property
    def command(self) -> CreatePayrollRunCommand | None:
        return self._cmd


class _NewOffCycleRunDialog(QDialog):
    """Capture the extra fields for :class:`CreateOffCyclePayrollRunCommand`.

    Does *not* support per-employee selection — the caller must pass in
    the employee IDs to include (typically the currently selected set in
    the People pane). For simplicity in this release the dialog collects
    all *active* employees; the service validates them.
    """

    def __init__(
        self,
        company_currency: str = "XAF",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Off-Cycle Payroll run")
        self.setMinimumWidth(DEFAULT_TOKENS.sizes.workbench_pane_min_w_wide)

        today = date.today()
        self._cmd: CreateOffCyclePayrollRunCommand | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        # Year
        self._year_spin = QSpinBox(self)
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(today.year)
        grid.addWidget(QLabel("Year", self), 0, 0)
        grid.addWidget(self._year_spin, 0, 1)

        # Month
        self._month_combo = QComboBox(self)
        for m in _MONTHS:
            self._month_combo.addItem(m)
        self._month_combo.setCurrentIndex(today.month - 1)
        grid.addWidget(QLabel("Month", self), 1, 0)
        grid.addWidget(self._month_combo, 1, 1)

        # Currency
        self._ccy_combo = QComboBox(self)
        for ccy in ("XAF", "USD", "EUR", "GBP", "XOF"):
            self._ccy_combo.addItem(ccy)
        idx = self._ccy_combo.findText(company_currency)
        if idx >= 0:
            self._ccy_combo.setCurrentIndex(idx)
        grid.addWidget(QLabel("Currency", self), 2, 0)
        grid.addWidget(self._ccy_combo, 2, 1)

        # Reason
        self._reason_combo = QComboBox(self)
        for code, label in _OFF_CYCLE_REASONS:
            self._reason_combo.addItem(label, code)
        grid.addWidget(QLabel("Reason *", self), 3, 0)
        grid.addWidget(self._reason_combo, 3, 1)

        layout.addLayout(grid)

        note = QLabel(
            "The off-cycle run will include all active employees by default. "
            "You can exclude individuals in the run cockpit after creation.",
            self,
        )
        note.setObjectName("DialogSectionSummary")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        year = self._year_spin.value()
        month = self._month_combo.currentIndex() + 1
        currency = self._ccy_combo.currentText()
        reason_code = self._reason_combo.currentData() or "other"
        month_name = _MONTHS[month - 1]
        reason_label = self._reason_combo.currentText()
        self._cmd = CreateOffCyclePayrollRunCommand(
            period_year=year,
            period_month=month,
            run_label=f"{month_name} {year} Off-cycle \u2014 {reason_label}",
            currency_code=currency,
            run_date=date.today(),
            employee_ids=(),  # Service will be called with active employees
            off_cycle_reason_code=reason_code,
        )
        self.accept()

    @property
    def command(self) -> CreateOffCyclePayrollRunCommand | None:
        return self._cmd


# ── Run pane ──────────────────────────────────────────────────────────────────

class RunPaneWidget(QWidget):
    """Native payroll run list pane for the workbench."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollRunPane")
        self._sr = service_registry
        self._model = _RunTableModel(self)

        self._build_ui()
        self.refresh()

    # ── Construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        tok = DEFAULT_TOKENS
        layout.setContentsMargins(
            tok.spacing.page_padding,
            tok.spacing.section_gap,
            tok.spacing.page_padding,
            tok.spacing.section_gap,
        )
        layout.setSpacing(tok.spacing.section_gap)

        # Toolbar
        toolbar = QFrame(self)
        toolbar.setObjectName("WorkbenchPaneToolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(tok.spacing.control_gap)

        self._new_btn = QPushButton("New Run", toolbar)
        self._new_btn.setObjectName("NewRunButton")
        self._new_btn.setAccessibleName("New payroll run")
        self._new_btn.setProperty("variant", "primary")
        self._new_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._new_btn.clicked.connect(self._on_new_run)
        tb_layout.addWidget(self._new_btn)

        self._new_offcycle_btn = QPushButton("New Off-Cycle Run", toolbar)
        self._new_offcycle_btn.setObjectName("NewOffCycleRunButton")
        self._new_offcycle_btn.setAccessibleName("New off-cycle payroll run")
        self._new_offcycle_btn.setProperty("variant", "secondary")
        self._new_offcycle_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._new_offcycle_btn.setEnabled(False)
        self._new_offcycle_btn.clicked.connect(self._on_new_offcycle_run)
        tb_layout.addWidget(self._new_offcycle_btn)

        self._open_btn = QPushButton("Open Run", toolbar)
        self._open_btn.setObjectName("OpenRunButton")
        self._open_btn.setAccessibleName("Open selected payroll run")
        self._open_btn.setProperty("variant", "secondary")
        self._open_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open_run)
        tb_layout.addWidget(self._open_btn)

        tb_layout.addStretch(1)

        self._count_label = QLabel("", toolbar)
        self._count_label.setObjectName("WorkbenchPaneCountLabel")
        tb_layout.addWidget(self._count_label)

        layout.addWidget(toolbar)

        # Table
        self._table = DataTable(
            columns=_COLUMNS,
            parent=self,
        )
        self._table.set_model(self._model)
        self._table.setObjectName("PayrollRunTable")
        self._table.setAccessibleName("Payroll runs list")
        self._table.selection_changed.connect(self._on_selection_changed)
        self._table.row_activated.connect(self._on_double_click)
        layout.addWidget(self._table, 1)

        # ── Keyboard shortcuts (P13.S2) ────────────────────────────────
        _sc = shortcut_map("payroll.run")
        if "new_run" in _sc:
            install_shortcut(self, _sc["new_run"], self._on_new_run)
        if "open_run" in _sc:
            install_shortcut(self, _sc["open_run"], self._on_open_run)
        # Density toggle (P13.S4)
        _tsc = shortcut_map("table")
        if "toggle_density" in _tsc:
            install_shortcut(
                self, _tsc["toggle_density"],
                lambda: self._table.set_density(
                    "comfortable" if self._table.density() == "dense" else "dense"
                ),
            )
        # Tab order: New Run → New Off-Cycle → Open Run → table search
        self.setTabOrder(self._new_btn, self._new_offcycle_btn)
        self.setTabOrder(self._new_offcycle_btn, self._open_btn)

    # ── Active company helpers ─────────────────────────────────────────

    def _active_company_id(self) -> int | None:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return None
        try:
            company = ctx.get_active_company()
            return getattr(company, "id", None) if company else None
        except Exception:
            return None

    def _active_company_currency(self) -> str:
        ctx = getattr(self._sr, "company_context_service", None)
        if ctx is None:
            return "XAF"
        try:
            company = ctx.get_active_company()
            if company is None:
                return "XAF"
            svc = getattr(self._sr, "payroll_setup_service", None)
            if svc is None:
                return "XAF"
            settings = svc.get_company_payroll_settings(getattr(company, "id", 0))
            if settings and getattr(settings, "currency_code", None):
                return settings.currency_code
        except Exception:
            pass
        return "XAF"

    # ── Public ────────────────────────────────────────────────────────

    def refresh(self) -> None:
        company_id = self._active_company_id()
        has_company = company_id is not None
        self._new_btn.setEnabled(has_company)
        self._new_offcycle_btn.setEnabled(has_company)

        if not has_company:
            self._model.load([])
            self._count_label.setText("")
            return

        svc = getattr(self._sr, "payroll_run_service", None)
        if svc is None:
            logger.warning("payroll_run_service not available in service registry")
            self._model.load([])
            self._count_label.setText("")
            return

        try:
            runs = svc.list_runs(company_id)
        except Exception:
            logger.warning("payroll_run_service.list_runs failed", exc_info=True)
            runs = []

        self._model.load(runs)
        n = len(runs)
        self._count_label.setText(f"{n} run{'s' if n != 1 else ''}")

    # ── Slot handlers ─────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        has_sel = bool(self._table.selected_rows())
        self._open_btn.setEnabled(has_sel)

    def _on_double_click(self) -> None:
        self._on_open_run()

    def _on_new_run(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            return
        currency = self._active_company_currency()
        dlg = _NewRunDialog(company_currency=currency, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cmd = dlg.command
        if cmd is None:
            return

        svc = getattr(self._sr, "payroll_run_service", None)
        if svc is None:
            logger.warning("payroll_run_service not available")
            return

        try:
            run_dto = svc.create_run(company_id, cmd)
        except Exception:
            logger.warning("create_run failed", exc_info=True)
            return

        self.refresh()
        self._open_cockpit(company_id, run_dto.id)

    def _on_new_offcycle_run(self) -> None:
        company_id = self._active_company_id()
        if company_id is None:
            return
        currency = self._active_company_currency()
        dlg = _NewOffCycleRunDialog(company_currency=currency, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cmd = dlg.command
        if cmd is None:
            return

        svc = getattr(self._sr, "payroll_run_service", None)
        if svc is None:
            logger.warning("payroll_run_service not available")
            return

        # Resolve active employees for this company to pass to the service.
        # The service validates each employee individually.
        employee_ids: tuple[int, ...] = ()
        emp_svc = getattr(self._sr, "employee_service", None)
        if emp_svc is not None:
            try:
                employees = emp_svc.list_employees(company_id, active_only=True)
                employee_ids = tuple(e.id for e in employees)
            except Exception:
                logger.warning("list_employees failed for off-cycle run", exc_info=True)

        if not employee_ids:
            from seeker_accounting.shared.ui.message_boxes import show_error
            show_error(
                self,
                "New Off-Cycle Run",
                "No active employees found. Ensure employees are set up before "
                "creating an off-cycle run.",
            )
            return

        # Rebuild command with resolved employee IDs.
        cmd = CreateOffCyclePayrollRunCommand(
            period_year=cmd.period_year,
            period_month=cmd.period_month,
            run_label=cmd.run_label,
            currency_code=cmd.currency_code,
            run_date=cmd.run_date,
            employee_ids=employee_ids,
            off_cycle_reason_code=cmd.off_cycle_reason_code,
            payment_date=cmd.payment_date,
            notes=cmd.notes,
            source_run_id=cmd.source_run_id,
        )

        try:
            run_dto = svc.create_offcycle_run(company_id, cmd)
        except Exception:
            logger.warning("create_offcycle_run failed", exc_info=True)
            from seeker_accounting.shared.ui.message_boxes import show_error
            show_error(self, "New Off-Cycle Run", "Could not create the off-cycle run.")
            return

        self.refresh()
        self._open_cockpit(company_id, run_dto.id)

    def _on_open_run(self) -> None:
        rows = self._table.selected_rows()
        if not rows:
            return
        dto = self._model.row_dto(rows[0])
        if dto is None:
            return
        company_id = self._active_company_id()
        if company_id is None:
            return
        self._open_cockpit(company_id, dto.id)

    def _open_cockpit(self, company_id: int, run_id: int) -> None:
        try:
            from seeker_accounting.modules.payroll.ui.payroll_run_cockpit_window import (
                PayrollRunCockpitWindow,
            )

            manager = getattr(self._sr, "child_window_manager", None)

            def _factory() -> PayrollRunCockpitWindow:
                return PayrollRunCockpitWindow(
                    self._sr,
                    company_id=company_id,
                    run_id=run_id,
                )

            if manager is not None:
                manager.open_document(PayrollRunCockpitWindow.DOC_TYPE, run_id, _factory)
            else:
                win = _factory()
                win.show()
        except Exception:
            logger.warning(
                "PayrollRunCockpitWindow unavailable for run %s", run_id, exc_info=True
            )
