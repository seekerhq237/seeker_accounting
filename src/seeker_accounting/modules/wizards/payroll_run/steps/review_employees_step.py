"""Step 2 — Review computed payslips before approval."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.payroll_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ReviewEmployeesStep(WizardStep):
    key = "review_employees"
    title = "Review Employees"
    subtitle = "Inspect computed totals before approving."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._summary: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        intro = QLabel(
            "These totals reflect the most recent calculation. Use the Payroll "
            "module's run editor to exclude individual employees before "
            "returning here to approve.",
            root,
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #4E5866; font-size: 11px;")
        outer.addWidget(intro)

        self._table = QTableWidget(0, 5, root)
        self._table.setHorizontalHeaderLabels(
            ["Employee #", "Name", "Status", "Gross", "Net"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self._table, 1)

        self._summary = QLabel("", root)
        self._summary.setStyleSheet("color: #2E3848; font-size: 12px; font-weight: 600;")
        outer.addWidget(self._summary)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None or self._summary is None:
            return
        run_id = state.get(K.KEY_RUN_ID)
        if not isinstance(run_id, int):
            self._summary.setText("No run is loaded.")
            return
        company_id = context.require_company_id()
        service = context.service_registry.payroll_run_service
        rows = service.list_run_employees(company_id, run_id)

        included = [r for r in rows if r.status_code != "excluded"]
        gross_total = sum((r.gross_earnings for r in included), Decimal("0"))
        net_total = sum((r.net_payable for r in included), Decimal("0"))

        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(row.employee_number))
            self._table.setItem(i, 1, QTableWidgetItem(row.employee_display_name))
            self._table.setItem(i, 2, QTableWidgetItem(row.status_code))
            gross = QTableWidgetItem(f"{row.gross_earnings:,.2f}")
            net = QTableWidgetItem(f"{row.net_payable:,.2f}")
            gross.setTextAlignment(0x0002 | 0x0080)
            net.setTextAlignment(0x0002 | 0x0080)
            self._table.setItem(i, 3, gross)
            self._table.setItem(i, 4, net)

        currency = state.get(K.KEY_CURRENCY_CODE) or ""
        self._summary.setText(
            f"{len(included)} included / {len(rows)} total  ·  "
            f"Gross: {gross_total:,.2f} {currency}  ·  Net: {net_total:,.2f} {currency}"
        )

        state[K.KEY_EMPLOYEE_COUNT] = len(included)
        state[K.KEY_TOTAL_GROSS] = str(gross_total)
        state[K.KEY_TOTAL_NET] = str(net_total)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_EMPLOYEE_COUNT):
            return StepValidationResult.fail("No included employees in this run.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        n = state.get(K.KEY_EMPLOYEE_COUNT, 0)
        net = state.get(K.KEY_TOTAL_NET) or "0"
        cur = state.get(K.KEY_CURRENCY_CODE) or ""
        return f"{n} employee(s) included; net payable {net} {cur}."
