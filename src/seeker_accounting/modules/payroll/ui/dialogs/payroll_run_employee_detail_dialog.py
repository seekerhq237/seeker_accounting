from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    PayrollRunEmployeeDetailDTO,
)
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_TYPE_LABELS = {
    "earning": "Earning",
    "deduction": "Deduction",
    "employer_contribution": "Employer Contribution",
    "tax": "Tax",
    "informational": "Informational",
}


class PayrollRunEmployeeDetailDialog(QDialog):
    """Show the full payroll calculation breakdown for one employee in a run."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        run_employee_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = service_registry
        self._company_id = company_id
        self._run_employee_id = run_employee_id

        self.setWindowTitle("Employee Payroll Detail")
        self.setMinimumSize(680, 560)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)

        self._header = QLabel()
        self._header.setStyleSheet("font-weight: 600; font-size: 13px;")
        layout.addWidget(self._header)

        self._bases_frame = QFrame()
        self._bases_frame.setFrameShape(QFrame.Shape.StyledPanel)
        bases_layout = QHBoxLayout(self._bases_frame)
        bases_layout.setContentsMargins(10, 8, 10, 8)
        bases_layout.setSpacing(20)
        self._bases: dict[str, QLabel] = {}
        for key in ("Gross Earnings", "CNPS Base", "TDL Base", "Taxable Base", "Employer Cost", "Net Payable"):
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
        layout.addWidget(self._bases_frame)

        # Lines table
        self._table = QTableWidget()
        configure_compact_table(self._table)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Component", "Type", "Basis", "Rate", "Amount"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        # Summary
        summary_frame = QFrame()
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(10, 6, 10, 6)
        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("font-size: 11px;")
        summary_layout.addWidget(self._summary_label)
        layout.addWidget(summary_frame)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)

        # Payslip preview button
        from PySide6.QtWidgets import QPushButton
        self._btn_payslip = QPushButton("Payslip Preview…")
        self._btn_payslip.setFixedHeight(26)
        self._btn_payslip.clicked.connect(self._on_payslip)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._btn_payslip)
        btn_row.addStretch()
        btn_row.addWidget(close)
        layout.addLayout(btn_row)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.payroll_run_employee_detail", dialog=True)

        self._detail: PayrollRunEmployeeDetailDTO | None = None
        self._load()

    def _load(self) -> None:
        try:
            detail = self._registry.payroll_run_service.get_run_employee_detail(
                self._company_id, self._run_employee_id
            )
        except Exception as exc:
            self._header.setText(f"Error: {exc}")
            return

        self._detail = detail
        self.setWindowTitle(f"Payroll Detail — {detail.employee_display_name}")
        self._header.setText(
            f"{detail.employee_number}  ·  {detail.employee_display_name}  ·  "
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
                QTableWidgetItem(_TYPE_LABELS.get(line.component_type_code, line.component_type_code))
            )
            basis = QTableWidgetItem(f"{line.calculation_basis:,.2f}")
            basis.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, basis)

            rate_text = f"{float(line.rate_applied) * 100:.4f}%" if line.rate_applied else ""
            rate_item = QTableWidgetItem(rate_text)
            rate_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, rate_item)

            amount = QTableWidgetItem(f"{line.component_amount:,.2f}")
            amount.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            # Color-code: deductions and taxes in amber/red
            if line.component_type_code in ("deduction", "tax"):
                amount.setForeground(Qt.GlobalColor.darkRed)
            elif line.component_type_code == "employer_contribution":
                amount.setForeground(Qt.GlobalColor.darkBlue)
            self._table.setItem(row, 4, amount)

        self._table.resizeColumnsToContents()

        self._summary_label.setText(
            f"Total Earnings: {fmt(detail.total_earnings)}   "
            f"Deductions: {fmt(detail.total_employee_deductions)}   "
            f"Taxes: {fmt(detail.total_taxes)}   "
            f"Net: {fmt(detail.net_payable)}"
        )

    def _on_payslip(self) -> None:
        if self._detail is None:
            return
        from seeker_accounting.modules.payroll.ui.dialogs.payslip_preview_dialog import PayslipPreviewDialog
        dlg = PayslipPreviewDialog(
            self._registry, self._company_id, self._run_employee_id, self
        )
        dlg.exec()
