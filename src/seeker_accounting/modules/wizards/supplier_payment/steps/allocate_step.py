"""Step 2 \u2014 Allocate the payment across open bills."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.supplier_payment import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)

_COL_NUMBER = 0
_COL_DATE = 1
_COL_DUE = 2
_COL_OPEN = 3
_COL_ALLOC = 4


class AllocateStep(WizardStep):
    key = "allocate"
    title = "Allocate"
    subtitle = "Apply the payment across open bills."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._amount_label: QLabel | None = None
        self._allocated_label: QLabel | None = None
        self._auto_btn: QPushButton | None = None
        self._bills: list = []

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._amount_label = QLabel("", root)
        self._amount_label.setStyleSheet("color: #2E3848; font-size: 12px; font-weight: 600;")
        outer.addWidget(self._amount_label)

        self._table = QTableWidget(0, 5, root)
        self._table.setHorizontalHeaderLabels(
            ["Bill #", "Date", "Due", "Open balance", "Allocate"]
        )
        self._table.verticalHeader().setVisible(False)
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(_COL_NUMBER, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(_COL_DATE, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(_COL_DUE, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(_COL_OPEN, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(_COL_ALLOC, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self._table, 1)

        self._auto_btn = QPushButton("Fill open balances", root)
        self._auto_btn.clicked.connect(self._auto_allocate)
        outer.addWidget(self._auto_btn)

        self._allocated_label = QLabel("Allocated: 0.00", root)
        self._allocated_label.setStyleSheet("color: #2E3848; font-size: 12px;")
        outer.addWidget(self._allocated_label)
        return root

    def _amount_paid(self, state: WizardState) -> Decimal:
        try:
            return Decimal(str(state.get(K.KEY_AMOUNT_PAID) or "0"))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None or self._amount_label is None:
            return
        company_id = context.require_company_id()
        supplier_id = state.get(K.KEY_SUPPLIER_ID)
        if not isinstance(supplier_id, int):
            self._table.setRowCount(0)
            self._amount_label.setText("No supplier selected.")
            return
        self._bills = list(
            context.service_registry.purchase_bill_service.list_open_bills_for_supplier(
                company_id, supplier_id
            )
        )
        amount = self._amount_paid(state)
        cur = state.get(K.KEY_CURRENCY_CODE) or ""
        self._amount_label.setText(
            f"Payment amount: {amount:,.2f} {cur} \u00b7 {len(self._bills)} open bill(s)"
        )

        prior = {
            int(a["bill_id"]): str(a.get("allocated", "0"))
            for a in (state.get(K.KEY_ALLOCATIONS) or [])
            if isinstance(a, dict) and "bill_id" in a
        }
        self._table.setRowCount(len(self._bills))
        for i, bill in enumerate(self._bills):
            self._table.setItem(i, _COL_NUMBER, QTableWidgetItem(bill.bill_number))
            self._table.setItem(i, _COL_DATE, QTableWidgetItem(bill.bill_date.isoformat()))
            self._table.setItem(i, _COL_DUE, QTableWidgetItem(bill.due_date.isoformat()))
            open_item = QTableWidgetItem(f"{bill.open_balance_amount:,.2f}")
            open_item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            self._table.setItem(i, _COL_OPEN, open_item)
            edit = QLineEdit()
            edit.setText(prior.get(bill.id, "0.00"))
            edit.textChanged.connect(self._refresh_totals)
            self._table.setCellWidget(i, _COL_ALLOC, edit)
        self._refresh_totals()

    def _iter_alloc_inputs(self):
        if self._table is None:
            return
        for i in range(self._table.rowCount()):
            w = self._table.cellWidget(i, _COL_ALLOC)
            if isinstance(w, QLineEdit):
                yield i, w

    def _refresh_totals(self) -> None:
        if self._allocated_label is None:
            return
        total = Decimal("0")
        for _, w in self._iter_alloc_inputs():
            try:
                total += Decimal(w.text().strip() or "0")
            except (InvalidOperation, ValueError):
                pass
        self._allocated_label.setText(f"Allocated: {total:,.2f}")

    def _auto_allocate(self) -> None:
        if self._table is None or not self._bills:
            return
        for i, w in self._iter_alloc_inputs():
            bill = self._bills[i]
            w.setText(f"{bill.open_balance_amount:.2f}")
        self._refresh_totals()

    def write_back(self, state: WizardState) -> None:
        rows = []
        for i, w in self._iter_alloc_inputs():
            bill = self._bills[i]
            text = w.text().strip()
            if not text:
                continue
            try:
                amt = Decimal(text)
            except (InvalidOperation, ValueError):
                amt = Decimal("0")
            if amt <= 0:
                continue
            rows.append(
                {
                    "bill_id": bill.id,
                    "bill_number": bill.bill_number,
                    "open_balance": str(bill.open_balance_amount),
                    "allocated": str(amt),
                }
            )
        state[K.KEY_ALLOCATIONS] = rows
        total = sum((Decimal(r["allocated"]) for r in rows), Decimal("0"))
        state[K.KEY_TOTAL_ALLOCATED] = str(total)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        amount = self._amount_paid(state)
        try:
            allocated = Decimal(str(state.get(K.KEY_TOTAL_ALLOCATED) or "0"))
        except (InvalidOperation, ValueError):
            return StepValidationResult.fail("Allocated total is invalid.")
        if allocated > amount:
            return StepValidationResult.fail(
                f"Allocated total ({allocated:,.2f}) exceeds the payment amount ({amount:,.2f})."
            )
        for row in state.get(K.KEY_ALLOCATIONS) or []:
            try:
                a = Decimal(str(row.get("allocated", "0")))
                ob = Decimal(str(row.get("open_balance", "0")))
            except (InvalidOperation, ValueError):
                return StepValidationResult.fail("An allocation amount is not a valid number.")
            if a > ob:
                return StepValidationResult.fail(
                    f"Allocation for bill {row.get('bill_number')} exceeds its open balance."
                )
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        n = len(state.get(K.KEY_ALLOCATIONS) or [])
        total = state.get(K.KEY_TOTAL_ALLOCATED) or "0"
        return f"{n} bill(s) allocated, total {total}."
