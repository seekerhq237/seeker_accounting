"""PayrollCalculationWorkspace — four-tab payroll run management workspace.

Tabs:
  1. Compensation Profiles   — employee salary profiles, effective-dated
  2. Recurring Components    — component assignments per employee
  3. Variable Inputs         — approved variable input batches and lines
  4. Payroll Runs            — run creation, calculation, approval, void

No GL posting here. This workspace handles data setup and calculation only.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.ui.dialogs.compensation_profile_dialog import (
    CompensationProfileDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.component_assignment_dialog import (
    ComponentAssignmentDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_input_batch_dialog import (
    NewPayrollInputBatchDialog,
    PayrollInputBatchDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_run_dialog import PayrollRunDialog
from seeker_accounting.modules.payroll.ui.dialogs.payroll_project_allocations_dialog import (
    PayrollProjectAllocationsDialog,
)
from seeker_accounting.modules.payroll.ui.dialogs.payroll_run_employee_detail_dialog import (
    PayrollRunEmployeeDetailDialog,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error, show_info
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_log = logging.getLogger(__name__)

_STATUS_CHIP = {
    "draft": "Draft",
    "approved": "Approved",
    "calculated": "Calculated",
    "voided": "Voided",
    "included": "OK",
    "excluded": "Excluded",
    "error": "Error",
}

_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


class PayrollCalculationWorkspace(QWidget):
    def __init__(
        self,
        service_registry: ServiceRegistry,
        stack: QStackedWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._stack = stack
        self._company_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        self._profiles_tab = _CompensationProfilesTab(service_registry, self)
        self._assignments_tab = _ComponentAssignmentsTab(service_registry, self)
        self._inputs_tab = _VariableInputsTab(service_registry, self)
        self._runs_tab = _PayrollRunsTab(service_registry, self)

        self._tabs.addTab(self._profiles_tab, "Compensation Profiles")
        self._tabs.addTab(self._assignments_tab, "Recurring Components")
        self._tabs.addTab(self._inputs_tab, "Variable Inputs")
        self._tabs.addTab(self._runs_tab, "Payroll Runs")

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._registry.active_company_context.active_company_changed.connect(
            self._on_active_company_changed
        )

        # Auto-select company from context
        ctx = self._registry.active_company_context
        if ctx.company_id:
            self._set_company(ctx.company_id, ctx.company_name or "")
        else:
            self._clear_company()


    def _set_company(self, company_id: int, company_name: str) -> None:
        self._company_id = company_id
        self._profiles_tab.set_company(company_id)
        self._assignments_tab.set_company(company_id)
        self._inputs_tab.set_company(company_id)
        self._runs_tab.set_company(company_id)

    def _clear_company(self) -> None:
        self._company_id = None

    def _on_active_company_changed(self, company_id: object, company_name: object) -> None:
        if isinstance(company_id, int) and company_id > 0:
            self._set_company(company_id, company_name if isinstance(company_name, str) else "")
            return
        self._clear_company()

    def _on_tab_changed(self, index: int) -> None:
        if self._company_id is None:
            return
        tab = self._tabs.widget(index)
        if hasattr(tab, "set_company"):
            tab.set_company(self._company_id)
        elif hasattr(tab, "refresh"):
            tab.refresh()


# ── Tab: Compensation Profiles ─────────────────────────────────────────────────

class _CompensationProfilesTab(QWidget):
    def __init__(self, registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self._emp_filter = QComboBox()
        self._emp_filter.setMinimumWidth(220)
        self._emp_filter.addItem("All Employees", None)
        self._emp_filter.currentIndexChanged.connect(self.refresh)
        filter_bar.addWidget(QLabel("Employee:"))
        filter_bar.addWidget(self._emp_filter)
        filter_bar.addStretch()

        self._btn_new = QPushButton("New Profile…")
        self._btn_new.setFixedHeight(26)
        self._btn_new.clicked.connect(self._on_new)
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setFixedHeight(26)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_toggle = QPushButton("Toggle Active")
        self._btn_toggle.setFixedHeight(26)
        self._btn_toggle.clicked.connect(self._on_toggle)

        filter_bar.addWidget(self._btn_new)
        filter_bar.addWidget(self._btn_edit)
        filter_bar.addWidget(self._btn_toggle)
        layout.addLayout(filter_bar)

        self._table = QTableWidget()
        configure_compact_table(self._table)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Employee", "Profile Name", "Basic Salary", "Currency", "From", "To", "Active"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_edit)
        layout.addWidget(self._table)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self._load_employee_filter()
        self.refresh()

    def _load_employee_filter(self) -> None:
        current_emp_id = self._emp_filter.currentData()  # preserve current selection
        self._emp_filter.blockSignals(True)
        self._emp_filter.clear()
        self._emp_filter.addItem("All Employees", None)
        try:
            employees = self._registry.employee_service.list_employees(
                self._company_id, active_only=True
            )
            for emp in employees:
                self._emp_filter.addItem(
                    f"{emp.employee_number} — {emp.display_name}", emp.id
                )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
        if current_emp_id is not None:
            for i in range(self._emp_filter.count()):
                if self._emp_filter.itemData(i) == current_emp_id:
                    self._emp_filter.setCurrentIndex(i)
                    break
        self._emp_filter.blockSignals(False)

    def refresh(self) -> None:
        if self._company_id is None:
            return
        emp_id = self._emp_filter.currentData()
        try:
            profiles = self._registry.compensation_profile_service.list_profiles(
                self._company_id, employee_id=emp_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._table.setRowCount(0)
        for p in profiles:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(p.employee_display_name))
            self._table.setItem(row, 1, QTableWidgetItem(p.profile_name))
            salary = QTableWidgetItem(f"{p.basic_salary:,.2f}")
            salary.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, salary)
            self._table.setItem(row, 3, QTableWidgetItem(p.currency_code))
            self._table.setItem(row, 4, QTableWidgetItem(str(p.effective_from)))
            self._table.setItem(row, 5, QTableWidgetItem(str(p.effective_to) if p.effective_to else "Open"))
            self._table.setItem(row, 6, QTableWidgetItem("Yes" if p.is_active else "No"))
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, p)

        self._table.resizeColumnsToContents()

    def _selected_profile(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_new(self) -> None:
        if self._company_id is None:
            return
        emp_id = self._emp_filter.currentData()
        if emp_id is None:
            show_error(self, "Payroll Calculation", "Select an employee filter first to create a profile.")
            return
        emp_name = self._emp_filter.currentText()
        dlg = CompensationProfileDialog(
            self._registry, self._company_id, emp_id, emp_name, None, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_edit(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        dlg = CompensationProfileDialog(
            self._registry, self._company_id, profile.employee_id,
            profile.employee_display_name, profile, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_toggle(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        try:
            self._registry.compensation_profile_service.toggle_profile_active(
                self._company_id, profile.id
            )
            self.refresh()
        except Exception as exc:
            show_error(self, "Payroll Calculation", str(exc))


# ── Tab: Component Assignments ─────────────────────────────────────────────────

class _ComponentAssignmentsTab(QWidget):
    def __init__(self, registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self._emp_filter = QComboBox()
        self._emp_filter.setMinimumWidth(220)
        self._emp_filter.currentIndexChanged.connect(self.refresh)
        filter_bar.addWidget(QLabel("Employee:"))
        filter_bar.addWidget(self._emp_filter)
        filter_bar.addStretch()

        self._btn_new = QPushButton("Assign Component…")
        self._btn_new.setFixedHeight(26)
        self._btn_new.clicked.connect(self._on_new)
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setFixedHeight(26)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_toggle = QPushButton("Toggle Active")
        self._btn_toggle.setFixedHeight(26)
        self._btn_toggle.clicked.connect(self._on_toggle)

        filter_bar.addWidget(self._btn_new)
        filter_bar.addWidget(self._btn_edit)
        filter_bar.addWidget(self._btn_toggle)
        layout.addLayout(filter_bar)

        self._table = QTableWidget()
        configure_compact_table(self._table)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Component", "Type", "Method", "Override Amt", "Override Rate", "From", "Active"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_edit)
        layout.addWidget(self._table)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self._load_employee_filter()
        self.refresh()

    def _load_employee_filter(self) -> None:
        self._emp_filter.blockSignals(True)
        self._emp_filter.clear()
        self._emp_filter.addItem("— Select Employee —", None)
        try:
            employees = self._registry.employee_service.list_employees(
                self._company_id, active_only=True
            )
            for emp in employees:
                self._emp_filter.addItem(
                    f"{emp.employee_number} — {emp.display_name}", emp.id
                )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
        self._emp_filter.blockSignals(False)

    def refresh(self) -> None:
        if self._company_id is None:
            return
        emp_id = self._emp_filter.currentData()
        if emp_id is None:
            self._table.setRowCount(0)
            return

        try:
            assignments = self._registry.component_assignment_service.list_assignments(
                self._company_id, emp_id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._table.setRowCount(0)
        for a in assignments:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(f"{a.component_code} — {a.component_name}"))
            self._table.setItem(row, 1, QTableWidgetItem(a.component_type_code))
            self._table.setItem(row, 2, QTableWidgetItem(a.calculation_method_code))
            ovr_amt = QTableWidgetItem(f"{a.override_amount:,.4f}" if a.override_amount else "")
            ovr_amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, ovr_amt)
            ovr_rate = QTableWidgetItem(f"{float(a.override_rate) * 100:.4f}%" if a.override_rate else "")
            ovr_rate.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, ovr_rate)
            self._table.setItem(row, 5, QTableWidgetItem(str(a.effective_from)))
            self._table.setItem(row, 6, QTableWidgetItem("Yes" if a.is_active else "No"))
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, a)

        self._table.resizeColumnsToContents()

    def _selected_assignment(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_new(self) -> None:
        emp_id = self._emp_filter.currentData()
        if emp_id is None:
            show_error(self, "Payroll Calculation", "Select an employee first.")
            return
        dlg = ComponentAssignmentDialog(self._registry, self._company_id, emp_id, None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_edit(self) -> None:
        a = self._selected_assignment()
        if a is None:
            return
        dlg = ComponentAssignmentDialog(self._registry, self._company_id, a.employee_id, a, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_toggle(self) -> None:
        a = self._selected_assignment()
        if a is None:
            return
        try:
            self._registry.component_assignment_service.toggle_active(self._company_id, a.id)
            self.refresh()
        except Exception as exc:
            show_error(self, "Payroll Calculation", str(exc))


# ── Tab: Variable Inputs ───────────────────────────────────────────────────────

class _VariableInputsTab(QWidget):
    def __init__(self, registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self._btn_new = QPushButton("New Batch…")
        self._btn_new.setFixedHeight(26)
        self._btn_new.clicked.connect(self._on_new)
        self._btn_open = QPushButton("Open / Manage…")
        self._btn_open.setFixedHeight(26)
        self._btn_open.clicked.connect(self._on_open)
        toolbar.addWidget(self._btn_new)
        toolbar.addWidget(self._btn_open)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableWidget()
        configure_compact_table(self._table)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Reference", "Period", "Status", "Description", "Lines", ""
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_open)
        layout.addWidget(self._table)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        if self._company_id is None:
            return
        try:
            batches = self._registry.payroll_input_service.list_batches(self._company_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._table.setRowCount(0)
        for b in batches:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(b.batch_reference))
            self._table.setItem(row, 1, QTableWidgetItem(
                f"{_MONTHS.get(b.period_month, str(b.period_month))} {b.period_year}"
            ))
            self._table.setItem(row, 2, QTableWidgetItem(_STATUS_CHIP.get(b.status_code, b.status_code)))
            self._table.setItem(row, 3, QTableWidgetItem(b.description or ""))
            count = QTableWidgetItem(str(b.line_count))
            count.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 4, count)
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, b.id)

        self._table.resizeColumnsToContents()

    def _selected_batch_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_new(self) -> None:
        if self._company_id is None:
            return
        dlg = NewPayrollInputBatchDialog(self._registry, self._company_id, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.created_batch_id:
            self.refresh()
            # Auto-open the new batch
            mgmt = PayrollInputBatchDialog(
                self._registry, self._company_id, dlg.created_batch_id, self
            )
            mgmt.exec()
            self.refresh()

    def _on_open(self) -> None:
        batch_id = self._selected_batch_id()
        if batch_id is None:
            return
        dlg = PayrollInputBatchDialog(self._registry, self._company_id, batch_id, self)
        dlg.exec()
        self.refresh()


# ── Tab: Payroll Runs ──────────────────────────────────────────────────────────

class _PayrollRunsTab(QWidget):
    def __init__(self, registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._company_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self._btn_new = QPushButton("New Run…")
        self._btn_new.setFixedHeight(26)
        self._btn_new.clicked.connect(self._on_new)
        self._btn_calculate = QPushButton("Calculate")
        self._btn_calculate.setFixedHeight(26)
        self._btn_calculate.clicked.connect(self._on_calculate)
        self._btn_approve = QPushButton("Approve")
        self._btn_approve.setFixedHeight(26)
        self._btn_approve.clicked.connect(self._on_approve)
        self._btn_void = QPushButton("Void")
        self._btn_void.setFixedHeight(26)
        self._btn_void.clicked.connect(self._on_void)
        self._btn_detail = QPushButton("Employee Detail…")
        self._btn_detail.setFixedHeight(26)
        self._btn_detail.clicked.connect(self._on_detail)
        self._btn_allocations = QPushButton("Project Allocations…")
        self._btn_allocations.setFixedHeight(26)
        self._btn_allocations.clicked.connect(self._on_allocations)

        for btn in (self._btn_new, self._btn_calculate, self._btn_approve,
                self._btn_void, self._btn_detail, self._btn_allocations):
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Runs table
        self._runs_table = QTableWidget()
        configure_compact_table(self._runs_table)
        self._runs_table.setColumnCount(7)
        self._runs_table.setHorizontalHeaderLabels([
            "Reference", "Period", "Status", "Employees", "Net Payable", "Run Date", "Currency"
        ])
        self._runs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._runs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._runs_table.selectionModel().selectionChanged.connect(self._on_run_selected)
        layout.addWidget(self._runs_table, 2)

        # Employees sub-table
        emp_header = QLabel("Employee Results (selected run)")
        emp_header.setStyleSheet("font-size: 11px; font-weight: 600; margin-top: 6px;")
        layout.addWidget(emp_header)

        self._emp_table = QTableWidget()
        configure_compact_table(self._emp_table)
        self._emp_table.setColumnCount(7)
        self._emp_table.setHorizontalHeaderLabels([
            "Employee", "Gross", "Deductions", "Taxes", "Net Payable", "Employer Cost", "Status"
        ])
        self._emp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._emp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._emp_table.doubleClicked.connect(self._on_detail)
        layout.addWidget(self._emp_table, 3)

    def set_company(self, company_id: int) -> None:
        self._company_id = company_id
        self.refresh()

    def refresh(self) -> None:
        if self._company_id is None:
            return
        try:
            runs = self._registry.payroll_run_service.list_runs(self._company_id)
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._runs_table.setRowCount(0)
        for r in runs:
            row = self._runs_table.rowCount()
            self._runs_table.insertRow(row)
            self._runs_table.setItem(row, 0, QTableWidgetItem(r.run_reference))
            self._runs_table.setItem(row, 1, QTableWidgetItem(
                f"{_MONTHS.get(r.period_month, str(r.period_month))} {r.period_year}"
            ))
            self._runs_table.setItem(row, 2, QTableWidgetItem(_STATUS_CHIP.get(r.status_code, r.status_code)))
            count = QTableWidgetItem(str(r.employee_count))
            count.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._runs_table.setItem(row, 3, count)
            net = QTableWidgetItem(f"{r.total_net_payable:,.2f}")
            net.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._runs_table.setItem(row, 4, net)
            self._runs_table.setItem(row, 5, QTableWidgetItem(str(r.run_date)))
            self._runs_table.setItem(row, 6, QTableWidgetItem(r.currency_code))
            self._runs_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, r)

        self._runs_table.resizeColumnsToContents()
        self._emp_table.setRowCount(0)

    def _selected_run(self):
        row = self._runs_table.currentRow()
        if row < 0:
            return None
        item = self._runs_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_run_employee_id(self) -> int | None:
        row = self._emp_table.currentRow()
        if row < 0:
            return None
        item = self._emp_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_run_selected(self) -> None:
        run = self._selected_run()
        if run is None:
            self._emp_table.setRowCount(0)
            return
        try:
            employees = self._registry.payroll_run_service.list_run_employees(
                self._company_id, run.id
            )
        except Exception:
            _log.warning("Form data load error", exc_info=True)
            return

        self._emp_table.setRowCount(0)
        for e in employees:
            row = self._emp_table.rowCount()
            self._emp_table.insertRow(row)
            self._emp_table.setItem(row, 0, QTableWidgetItem(e.employee_display_name))
            for col, val in enumerate((
                e.gross_earnings, e.total_employee_deductions, e.total_taxes,
                e.net_payable, e.employer_cost_base
            ), start=1):
                item = QTableWidgetItem(f"{val:,.2f}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._emp_table.setItem(row, col, item)
            self._emp_table.setItem(row, 6, QTableWidgetItem(
                _STATUS_CHIP.get(e.status_code, e.status_code)
            ))
            self._emp_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, e.id)

        self._emp_table.resizeColumnsToContents()

    def _on_new(self) -> None:
        if self._company_id is None:
            return
        dlg = PayrollRunDialog(self._registry, self._company_id, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _on_calculate(self) -> None:
        run = self._selected_run()
        if run is None:
            return
        if run.status_code not in ("draft", "calculated"):
            show_error(self, "Payroll Calculation", "Only draft or calculated runs can be recalculated.")
            return
        if QMessageBox.question(
            self, "Calculate Run",
            f"Calculate payroll for {run.run_label}?\n\nAll active employees will be processed."
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_run_service.calculate_run(self._company_id, run.id)
            show_info(self, "Payroll calculation complete.")
            self.refresh()
        except Exception as exc:
            show_error(self, "Payroll Calculation", str(exc))

    def _on_approve(self) -> None:
        run = self._selected_run()
        if run is None:
            return
        if run.status_code != "calculated":
            show_error(self, "Payroll Calculation", "Only calculated runs can be approved.")
            return
        if QMessageBox.question(
            self, "Approve Run",
            f"Approve payroll run {run.run_reference}? This cannot be undone."
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_run_service.approve_run(self._company_id, run.id)
            self.refresh()
        except Exception as exc:
            show_error(self, "Payroll Calculation", str(exc))

    def _on_void(self) -> None:
        run = self._selected_run()
        if run is None:
            return
        if QMessageBox.question(
            self, "Void Run", f"Void run {run.run_reference}?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._registry.payroll_run_service.void_run(self._company_id, run.id)
            self.refresh()
        except Exception as exc:
            show_error(self, "Payroll Calculation", str(exc))

    def _on_detail(self) -> None:
        run_emp_id = self._selected_run_employee_id()
        if run_emp_id is None:
            return
        dlg = PayrollRunEmployeeDetailDialog(
            self._registry, self._company_id, run_emp_id, self
        )
        dlg.exec()

    def _on_allocations(self) -> None:
        run_emp_id = self._selected_run_employee_id()
        if run_emp_id is None:
            show_error(self, "Project Allocations", "Select an employee row first.")
            return
        dlg = PayrollProjectAllocationsDialog(
            self._registry,
            self._company_id,
            run_emp_id,
            self,
        )
        dlg.exec()
