"""Step 2 — Lines (description, qty, unit cost, expense account, tax code)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.purchase_credit_note import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_HEADERS = ["Description", "Qty", "Unit cost", "Expense account", "Tax code", "Line subtotal"]


class LinesStep(WizardStep):
    key = "lines"
    title = "Lines"
    subtitle = "Credit note line items (debited expense / asset accounts to reverse)."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._add_btn: QPushButton | None = None
        self._remove_btn: QPushButton | None = None
        self._total_label: QLabel | None = None
        self._accounts: list[tuple[int, str, str]] = []
        self._tax_codes: list[tuple[int, str, str]] = []

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._table = QTableWidget(0, len(_HEADERS), root)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        outer.addWidget(self._table, 1)

        controls = QHBoxLayout()
        self._add_btn = QPushButton("+ Add line", root)
        self._remove_btn = QPushButton("\u2212 Remove selected", root)
        controls.addWidget(self._add_btn)
        controls.addWidget(self._remove_btn)
        controls.addStretch(1)
        self._total_label = QLabel("Total: 0.00", root)
        controls.addWidget(self._total_label)
        outer.addLayout(controls)

        self._add_btn.clicked.connect(self._on_add_row)
        self._remove_btn.clicked.connect(self._on_remove_row)
        self._table.itemChanged.connect(self._on_item_changed)
        return root

    # ---- helpers ----

    def _populate_account_combo(self, combo: QComboBox, current: int | None) -> None:
        combo.addItem("(pick)", None)
        for acc_id, code, name in self._accounts:
            combo.addItem(f"{code} \u2014 {name}", acc_id)
        if current is not None:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(lambda _i: self._refresh_total())

    def _populate_tax_combo(self, combo: QComboBox, current: int | None) -> None:
        combo.addItem("(none)", None)
        for tc_id, code, label in self._tax_codes:
            combo.addItem(f"{code} \u2014 {label}", tc_id)
        if current is not None:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(lambda _i: self._refresh_total())

    def _add_row(self, line: dict | None = None) -> None:
        assert self._table is not None
        row = self._table.rowCount()
        self._table.insertRow(row)
        # Description
        desc_item = QTableWidgetItem(str((line or {}).get("description", "")))
        self._table.setItem(row, 0, desc_item)
        # Qty
        qty_item = QTableWidgetItem(str((line or {}).get("quantity", "1")))
        qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, 1, qty_item)
        # Unit cost
        uc_item = QTableWidgetItem(str((line or {}).get("unit_cost", "0.00")))
        uc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, 2, uc_item)
        # Expense account combo
        acc_combo = QComboBox()
        self._populate_account_combo(acc_combo, (line or {}).get("expense_account_id"))
        self._table.setCellWidget(row, 3, acc_combo)
        # Tax combo
        tax_combo = QComboBox()
        self._populate_tax_combo(tax_combo, (line or {}).get("tax_code_id"))
        self._table.setCellWidget(row, 4, tax_combo)
        # Line subtotal (read-only)
        total_item = QTableWidgetItem("0.00")
        total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, 5, total_item)

    def _on_add_row(self) -> None:
        self._add_row()
        self._refresh_total()

    def _on_remove_row(self) -> None:
        if self._table is None:
            return
        rows = sorted({i.row() for i in self._table.selectedItems()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)
        self._refresh_total()

    def _on_item_changed(self, _it: QTableWidgetItem) -> None:
        self._refresh_total()

    def _row_amount(self, row: int) -> Decimal:
        if self._table is None:
            return Decimal(0)
        try:
            qty = Decimal(self._table.item(row, 1).text() if self._table.item(row, 1) else "0")
            uc = Decimal(self._table.item(row, 2).text() if self._table.item(row, 2) else "0")
            return qty * uc
        except (InvalidOperation, ValueError, AttributeError):
            return Decimal(0)

    def _refresh_total(self) -> None:
        if self._table is None or self._total_label is None:
            return
        total = Decimal(0)
        for row in range(self._table.rowCount()):
            amt = self._row_amount(row)
            total += amt
            cell = self._table.item(row, 5)
            if cell is not None:
                cell.setText(f"{amt:.2f}")
        self._total_label.setText(f"Subtotal: {total:.2f}")

    # ---- WizardStep overrides ----

    def load(self, context: WizardContext, state: WizardState) -> None:
        if not self._accounts:
            company_id = context.require_company_id()
            for a in context.service_registry.chart_of_accounts_service.list_accounts(
                company_id, active_only=True
            ):
                cls = (a.account_class_code or "").upper()
                if a.is_active and a.allow_manual_posting and cls in {"EXPENSE", "EXPENSES", "COST", "COSTS"}:
                    self._accounts.append((a.id, a.account_code, a.account_name))
            # Fallback: include all postable if expense class isn't tagged that way
            if not self._accounts:
                for a in context.service_registry.chart_of_accounts_service.list_accounts(
                    company_id, active_only=True
                ):
                    if a.is_active and a.allow_manual_posting:
                        self._accounts.append((a.id, a.account_code, a.account_name))
            for t in context.service_registry.tax_setup_service.list_tax_codes(
                company_id, active_only=True
            ):
                rate = f"{t.rate_percent}%" if t.rate_percent is not None else t.tax_type_code
                self._tax_codes.append((t.id, t.code, f"{t.name} ({rate})"))
        if self._table is not None and self._table.rowCount() == 0:
            existing = state.get(K.KEY_LINES) or []
            if isinstance(existing, list) and existing:
                for ln in existing:
                    if isinstance(ln, dict):
                        self._add_row(ln)
            else:
                self._add_row()
        self._refresh_total()

    def write_back(self, state: WizardState) -> None:
        if self._table is None:
            return
        lines: list[dict] = []
        for row in range(self._table.rowCount()):
            desc = (self._table.item(row, 0).text() if self._table.item(row, 0) else "").strip()
            qty_txt = (self._table.item(row, 1).text() if self._table.item(row, 1) else "").strip()
            uc_txt = (self._table.item(row, 2).text() if self._table.item(row, 2) else "").strip()
            acc_combo = self._table.cellWidget(row, 3)
            tax_combo = self._table.cellWidget(row, 4)
            acc_data = acc_combo.currentData() if isinstance(acc_combo, QComboBox) else None
            tax_data = tax_combo.currentData() if isinstance(tax_combo, QComboBox) else None
            lines.append(
                {
                    "description": desc,
                    "quantity": qty_txt,
                    "unit_cost": uc_txt,
                    "expense_account_id": int(acc_data) if isinstance(acc_data, int) else None,
                    "tax_code_id": int(tax_data) if isinstance(tax_data, int) else None,
                }
            )
        state[K.KEY_LINES] = lines

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        lines = state.get(K.KEY_LINES) or []
        if not lines:
            return StepValidationResult.fail("Add at least one line.")
        for i, ln in enumerate(lines, start=1):
            if not ln.get("description"):
                return StepValidationResult.fail(f"Line {i}: description is required.")
            try:
                qty = Decimal(str(ln.get("quantity") or "0"))
                uc = Decimal(str(ln.get("unit_cost") or "0"))
            except (InvalidOperation, ValueError):
                return StepValidationResult.fail(f"Line {i}: quantity and unit cost must be numbers.")
            if qty <= 0:
                return StepValidationResult.fail(f"Line {i}: quantity must be positive.")
            if uc < 0:
                return StepValidationResult.fail(f"Line {i}: unit cost cannot be negative.")
            if not isinstance(ln.get("expense_account_id"), int):
                return StepValidationResult.fail(f"Line {i}: pick an expense account.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        lines = state.get(K.KEY_LINES) or []
        if not lines:
            return None
        total = Decimal(0)
        for ln in lines:
            try:
                total += Decimal(str(ln.get("quantity") or "0")) * Decimal(str(ln.get("unit_cost") or "0"))
            except (InvalidOperation, ValueError):
                continue
        return f"{len(lines)} line(s); subtotal {total:.2f}"
