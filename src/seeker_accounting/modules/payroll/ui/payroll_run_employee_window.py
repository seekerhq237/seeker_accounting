"""PayrollRunEmployeeWindow — child-window replacement for the employee detail dialog.

Promoted from :class:`PayrollRunEmployeeDetailDialog` in Slice P2. Shows
the full payroll calculation breakdown for a single run-employee record,
and exposes payslip preview + project allocations through the child
window's ribbon instead of inline toolbar buttons.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.child_windows.child_window_base import ChildWindowBase
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    PayrollRunEmployeeDetailDTO,
)
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


_log = logging.getLogger(__name__)

_TYPE_LABELS = {
    "earning": "Earning",
    "deduction": "Deduction",
    "employer_contribution": "Employer Contribution",
    "tax": "Tax",
    "informational": "Informational",
}


class PayrollRunEmployeeWindow(ChildWindowBase):
    """Child-window replacement for :class:`PayrollRunEmployeeDetailDialog`."""

    DOC_TYPE = "payroll_run_employee"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        company_id: int,
        run_employee_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title="Employee Payroll Detail",
            surface_key=RibbonRegistry.child_window_key(self.DOC_TYPE),
            window_key=(self.DOC_TYPE, run_employee_id),
            registry=service_registry.ribbon_registry or RibbonRegistry(),
            icon_provider=IconProvider(service_registry.theme_manager),
            parent=parent,
        )
        self._registry = service_registry
        self._company_id = company_id
        self._run_employee_id = run_employee_id
        self._detail: PayrollRunEmployeeDetailDTO | None = None

        self.set_body(self._build_body())
        self._reload()

    # ── Body ──────────────────────────────────────────────────────────

    def _build_body(self) -> QWidget:
        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hero = QFrame(body)
        hero.setObjectName("DialogSectionCard")
        hero.setProperty("card", True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(4)
        self._title_label = QLabel("Employee Payroll Detail", hero)
        self._title_label.setObjectName("DialogSectionTitle")
        hero_layout.addWidget(self._title_label)
        self._summary_label = QLabel(hero)
        self._summary_label.setObjectName("DialogSectionSummary")
        self._summary_label.setWordWrap(True)
        hero_layout.addWidget(self._summary_label)
        layout.addWidget(hero)

        # Base metrics row
        bases_frame = QFrame(body)
        bases_frame.setFrameShape(QFrame.Shape.StyledPanel)
        bases_layout = QHBoxLayout(bases_frame)
        bases_layout.setContentsMargins(10, 8, 10, 8)
        bases_layout.setSpacing(20)
        self._bases: dict[str, QLabel] = {}
        for key in (
            "Gross Earnings", "CNPS Base", "TDL Base",
            "Taxable Base", "Employer Cost", "Net Payable",
        ):
            col = QVBoxLayout()
            col.setSpacing(2)
            title = QLabel(key)
            title.setStyleSheet("font-size: 10px; color: #666;")
            val = QLabel("—")
            val.setStyleSheet("font-weight: 600; font-size: 12px;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            col.addWidget(title)
            col.addWidget(val)
            self._bases[key] = val
            bases_layout.addLayout(col)
        layout.addWidget(bases_frame)

        # Lines table
        self._table = QTableWidget(body)
        configure_compact_table(self._table)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ("Component", "Type", "Basis", "Rate", "Amount")
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)

        self._totals_label = QLabel("", body)
        self._totals_label.setObjectName("DialogSectionSummary")
        layout.addWidget(self._totals_label)

        return body

    # ── Data ──────────────────────────────────────────────────────────

    def _reload(self) -> None:
        try:
            detail = self._registry.payroll_run_service.get_run_employee_detail(
                self._company_id, self._run_employee_id
            )
        except Exception as exc:  # noqa: BLE001 — surface any load failure
            show_error(self, "Employee Payroll Detail", str(exc))
            return

        self._detail = detail
        self.setWindowTitle(f"Payroll Detail — {detail.employee_display_name}")
        self._title_label.setText(
            f"{detail.employee_number} — {detail.employee_display_name}"
        )
        self._summary_label.setText(
            f"Run: {detail.run_reference}  ·  Status: {detail.status_code.upper()}"
        )

        def fmt(v) -> str:
            return f"{v:,.0f}"

        self._bases["Gross Earnings"].setText(fmt(detail.gross_earnings))
        self._bases["CNPS Base"].setText(fmt(detail.cnps_contributory_base))
        self._bases["TDL Base"].setText(fmt(detail.tdl_base))
        self._bases["Taxable Base"].setText(fmt(detail.taxable_salary_base))
        self._bases["Employer Cost"].setText(fmt(detail.employer_cost_base))
        self._bases["Net Payable"].setText(fmt(detail.net_payable))

        self._table.setRowCount(0)
        for line in sorted(detail.lines, key=lambda l: l.component_type_code):
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(line.component_name))
            self._table.setItem(
                row, 1,
                QTableWidgetItem(
                    _TYPE_LABELS.get(line.component_type_code, line.component_type_code)
                ),
            )
            basis = QTableWidgetItem(f"{line.calculation_basis:,.2f}")
            basis.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, basis)

            rate_text = (
                f"{float(line.rate_applied) * 100:.4f}%" if line.rate_applied else ""
            )
            rate_item = QTableWidgetItem(rate_text)
            rate_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, rate_item)

            amount = QTableWidgetItem(f"{line.component_amount:,.2f}")
            amount.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if line.component_type_code in ("deduction", "tax"):
                amount.setForeground(Qt.GlobalColor.darkRed)
            elif line.component_type_code == "employer_contribution":
                amount.setForeground(Qt.GlobalColor.darkBlue)
            self._table.setItem(row, 4, amount)

        self._table.resizeColumnsToContents()
        self._totals_label.setText(
            f"Total Earnings: {fmt(detail.total_earnings)}   "
            f"Deductions: {fmt(detail.total_employee_deductions)}   "
            f"Taxes: {fmt(detail.total_taxes)}   "
            f"Net: {fmt(detail.net_payable)}"
        )
        self.refresh_ribbon_state()

    # ── Ribbon host implementation ────────────────────────────────────

    def handle_ribbon_command(self, command_id: str) -> None:  # type: ignore[override]
        dispatch = {
            "payroll_run_employee.payslip_preview":     self._on_payslip_preview,
            "payroll_run_employee.project_allocations": self._on_project_allocations,
            "payroll_run_employee.refresh":             self._reload,
            "payroll_run_employee.close":               self.close,
        }
        handler = dispatch.get(command_id)
        if handler is not None:
            handler()

    def ribbon_state(self) -> dict[str, bool]:  # type: ignore[override]
        loaded = self._detail is not None
        return {
            "payroll_run_employee.payslip_preview":     loaded,
            "payroll_run_employee.project_allocations": loaded,
            "payroll_run_employee.refresh":             True,
            "payroll_run_employee.close":               True,
        }

    # ── Command handlers ──────────────────────────────────────────────

    def _on_payslip_preview(self) -> None:
        if self._detail is None:
            return
        from seeker_accounting.modules.payroll.ui.dialogs.payslip_preview_dialog import (
            PayslipPreviewDialog,
        )
        dlg = PayslipPreviewDialog(
            self._registry, self._company_id, self._run_employee_id, self
        )
        dlg.exec()

    def _on_project_allocations(self) -> None:
        if self._detail is None:
            return
        from seeker_accounting.modules.payroll.ui.dialogs.payroll_project_allocations_dialog import (
            PayrollProjectAllocationsDialog,
        )
        dlg = PayrollProjectAllocationsDialog(
            self._registry, self._company_id, self._run_employee_id, self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload()
