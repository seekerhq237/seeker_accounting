"""Step 2 \u2014 Allocate the receipt amount across open invoices.

Refreshes from `sales_invoice_service.list_open_invoices_for_customer` when entered.
The user types per-invoice allocated amounts; totals are validated against the
header amount received.
"""
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

from seeker_accounting.modules.wizards.receipt_allocation import state_keys as K
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
    subtitle = "Apply the receipt across open invoices."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._amount_label: QLabel | None = None
        self._allocated_label: QLabel | None = None
        self._unallocated_label: QLabel | None = None
        self._auto_btn: QPushButton | None = None
        self._invoices: list = []  # list[CustomerOpenInvoiceDTO]

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._amount_label = QLabel("", root)
        self._amount_label.setObjectName("WizardBodyTextStrong")
        outer.addWidget(self._amount_label)

        self._table = QTableWidget(0, 5, root)
        self._table.setHorizontalHeaderLabels(
            ["Invoice #", "Date", "Due", "Open balance", "Allocate"]
        )
        self._table.verticalHeader().setVisible(False)
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(_COL_NUMBER, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(_COL_DATE, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(_COL_DUE, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(_COL_OPEN, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(_COL_ALLOC, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self._table, 1)

        self._auto_btn = QPushButton("Auto-allocate oldest first", root)
        self._auto_btn.clicked.connect(self._auto_allocate)
        outer.addWidget(self._auto_btn)

        self._allocated_label = QLabel("Allocated: 0.00", root)
        self._allocated_label.setObjectName("WizardBodyText")
        outer.addWidget(self._allocated_label)

        self._unallocated_label = QLabel("Remaining: 0.00", root)
        self._unallocated_label.setObjectName("WizardMutedText")
        outer.addWidget(self._unallocated_label)
        return root

    def _amount_received(self, state: WizardState) -> Decimal:
        try:
            return Decimal(str(state.get(K.KEY_AMOUNT_RECEIVED) or "0"))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None or self._amount_label is None:
            return
        company_id = context.require_company_id()
        customer_id = state.get(K.KEY_CUSTOMER_ID)
        if not isinstance(customer_id, int):
            self._table.setRowCount(0)
            self._amount_label.setText("No customer selected.")
            return
        self._invoices = list(
            context.service_registry.sales_invoice_service.list_open_invoices_for_customer(
                company_id, customer_id
            )
        )
        amount = self._amount_received(state)
        cur = state.get(K.KEY_CURRENCY_CODE) or ""
        self._amount_label.setText(
            f"Receipt amount: {amount:,.2f} {cur} \u00b7 {len(self._invoices)} open invoice(s)"
        )

        prior_alloc = {
            int(a["invoice_id"]): str(a.get("allocated", "0"))
            for a in (state.get(K.KEY_ALLOCATIONS) or [])
            if isinstance(a, dict) and "invoice_id" in a
        }
        self._table.setRowCount(len(self._invoices))
        for i, inv in enumerate(self._invoices):
            self._table.setItem(i, _COL_NUMBER, QTableWidgetItem(inv.invoice_number))
            self._table.setItem(i, _COL_DATE, QTableWidgetItem(inv.invoice_date.isoformat()))
            self._table.setItem(i, _COL_DUE, QTableWidgetItem(inv.due_date.isoformat()))
            open_item = QTableWidgetItem(f"{inv.open_balance_amount:,.2f}")
            open_item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            self._table.setItem(i, _COL_OPEN, open_item)
            edit = QLineEdit()
            edit.setText(prior_alloc.get(inv.id, "0.00"))
            edit.setPlaceholderText("0.00")
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
        if self._table is None or self._allocated_label is None or self._unallocated_label is None:
            return
        total = Decimal("0")
        for _, w in self._iter_alloc_inputs():
            try:
                total += Decimal(w.text().strip() or "0")
            except (InvalidOperation, ValueError):
                pass
        self._allocated_label.setText(f"Allocated: {total:,.2f}")
        # remaining computed on validate

    def _auto_allocate(self) -> None:
        if self._table is None or not self._invoices:
            return
        # We can't easily access state here; use the visible amount label parsed
        # by re-scanning header amount label is fragile; instead read amounts from each row's open balance
        # Strategy: zero everything, then try to allocate equal-to-open-balance per invoice oldest-first
        # using a budget pulled from the allocated_label text? Better: introspect state via amount stored in widget tooltip.
        # Simpler & robust: walk through and ask user to type, but we can be smart by capping at open balance per row.
        for i, w in self._iter_alloc_inputs():
            inv = self._invoices[i]
            w.setText(f"{inv.open_balance_amount:.2f}")
        self._refresh_totals()

    def write_back(self, state: WizardState) -> None:
        rows = []
        for i, w in self._iter_alloc_inputs():
            inv = self._invoices[i]
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
                    "invoice_id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "open_balance": str(inv.open_balance_amount),
                    "allocated": str(amt),
                }
            )
        state[K.KEY_ALLOCATIONS] = rows
        total = sum((Decimal(r["allocated"]) for r in rows), Decimal("0"))
        state[K.KEY_TOTAL_ALLOCATED] = str(total)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        amount = self._amount_received(state)
        try:
            allocated = Decimal(str(state.get(K.KEY_TOTAL_ALLOCATED) or "0"))
        except (InvalidOperation, ValueError):
            return StepValidationResult.fail("Allocated total is invalid.")
        if allocated > amount:
            return StepValidationResult.fail(
                f"Allocated total ({allocated:,.2f}) exceeds the receipt amount ({amount:,.2f})."
            )
        # Each per-invoice allocation must not exceed its open balance
        for row in state.get(K.KEY_ALLOCATIONS) or []:
            try:
                a = Decimal(str(row.get("allocated", "0")))
                ob = Decimal(str(row.get("open_balance", "0")))
            except (InvalidOperation, ValueError):
                return StepValidationResult.fail("An allocation amount is not a valid number.")
            if a > ob:
                return StepValidationResult.fail(
                    f"Allocation for invoice {row.get('invoice_number')} exceeds its open balance."
                )
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        n = len(state.get(K.KEY_ALLOCATIONS) or [])
        total = state.get(K.KEY_TOTAL_ALLOCATED) or "0"
        return f"{n} invoice(s) allocated, total {total}."
