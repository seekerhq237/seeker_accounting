"""Step 2 — Lines (account, debit, credit) — must balance to zero."""
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

from seeker_accounting.modules.wizards.opening_balances import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.styles.inline_styles import text_style


_HEADERS = ["Account", "Description", "Debit", "Credit"]


class LinesStep(WizardStep):
    key = "lines"
    title = "Lines"
    subtitle = "Account-by-account opening balances. Debits must equal credits."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._add_btn: QPushButton | None = None
        self._remove_btn: QPushButton | None = None
        self._totals: QLabel | None = None
        self._accounts: list[tuple[int, str, str]] = []

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._table = QTableWidget(0, len(_HEADERS), root)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        outer.addWidget(self._table, 1)

        controls = QHBoxLayout()
        self._add_btn = QPushButton("+ Add line", root)
        self._remove_btn = QPushButton("\u2212 Remove selected", root)
        controls.addWidget(self._add_btn)
        controls.addWidget(self._remove_btn)
        controls.addStretch(1)
        self._totals = QLabel("Debits: 0.00 \u00b7 Credits: 0.00 \u00b7 Diff: 0.00", root)
        controls.addWidget(self._totals)
        outer.addLayout(controls)

        self._add_btn.clicked.connect(self._on_add)
        self._remove_btn.clicked.connect(self._on_remove)
        self._table.itemChanged.connect(self._on_item_changed)
        return root

    def _populate_account_combo(self, combo: QComboBox, current: int | None) -> None:
        combo.addItem("(pick)", None)
        for acc_id, code, name in self._accounts:
            combo.addItem(f"{code} \u2014 {name}", acc_id)
        if current is not None:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _add_row(self, line: dict | None = None) -> None:
        assert self._table is not None
        row = self._table.rowCount()
        self._table.insertRow(row)
        # Account combo
        acc_combo = QComboBox()
        self._populate_account_combo(acc_combo, (line or {}).get("account_id"))
        self._table.setCellWidget(row, 0, acc_combo)
        # Description
        desc_item = QTableWidgetItem(str((line or {}).get("line_description") or ""))
        self._table.setItem(row, 1, desc_item)
        # Debit
        dr_item = QTableWidgetItem(str((line or {}).get("debit_amount") or ""))
        dr_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, 2, dr_item)
        # Credit
        cr_item = QTableWidgetItem(str((line or {}).get("credit_amount") or ""))
        cr_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, 3, cr_item)

    def _on_add(self) -> None:
        self._add_row()
        self._refresh_totals()

    def _on_remove(self) -> None:
        if self._table is None:
            return
        rows = sorted({i.row() for i in self._table.selectedItems()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)
        self._refresh_totals()

    def _on_item_changed(self, _it: QTableWidgetItem) -> None:
        self._refresh_totals()

    def _safe_decimal(self, text: str) -> Decimal:
        text = (text or "").strip()
        if not text:
            return Decimal(0)
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return Decimal(0)

    def _refresh_totals(self) -> None:
        if self._table is None or self._totals is None:
            return
        dr = Decimal(0)
        cr = Decimal(0)
        for row in range(self._table.rowCount()):
            dr_cell = self._table.item(row, 2)
            cr_cell = self._table.item(row, 3)
            dr += self._safe_decimal(dr_cell.text() if dr_cell else "")
            cr += self._safe_decimal(cr_cell.text() if cr_cell else "")
        diff = dr - cr
        self._totals.setText(f"Debits: {dr:.2f} \u00b7 Credits: {cr:.2f} \u00b7 Diff: {diff:.2f}")
        self._totals.setStyleSheet(text_style("success" if diff == 0 and dr > 0 else "danger"))

    def load(self, context: WizardContext, state: WizardState) -> None:
        if not self._accounts:
            company_id = context.require_company_id()
            for a in context.service_registry.chart_of_accounts_service.list_accounts(
                company_id, active_only=True
            ):
                if a.is_active and a.allow_manual_posting:
                    self._accounts.append((a.id, a.account_code, a.account_name))
        if self._table is not None and self._table.rowCount() == 0:
            existing = state.get(K.KEY_LINES) or []
            if isinstance(existing, list) and existing:
                for ln in existing:
                    if isinstance(ln, dict):
                        self._add_row(ln)
            else:
                self._add_row()
                self._add_row()
        self._refresh_totals()

    def write_back(self, state: WizardState) -> None:
        if self._table is None:
            return
        lines: list[dict] = []
        for row in range(self._table.rowCount()):
            acc_combo = self._table.cellWidget(row, 0)
            acc_data = acc_combo.currentData() if isinstance(acc_combo, QComboBox) else None
            desc = self._table.item(row, 1).text().strip() if self._table.item(row, 1) else ""
            dr_txt = self._table.item(row, 2).text().strip() if self._table.item(row, 2) else ""
            cr_txt = self._table.item(row, 3).text().strip() if self._table.item(row, 3) else ""
            lines.append(
                {
                    "account_id": int(acc_data) if isinstance(acc_data, int) else None,
                    "line_description": desc or None,
                    "debit_amount": dr_txt or None,
                    "credit_amount": cr_txt or None,
                }
            )
        state[K.KEY_LINES] = lines

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        lines = state.get(K.KEY_LINES) or []
        if len([ln for ln in lines if ln.get("account_id")]) < 2:
            return StepValidationResult.fail("Add at least two account lines (one debit, one credit).")
        dr_total = Decimal(0)
        cr_total = Decimal(0)
        for i, ln in enumerate(lines, start=1):
            if not ln.get("account_id"):
                continue
            try:
                dr = Decimal(str(ln.get("debit_amount") or "0"))
                cr = Decimal(str(ln.get("credit_amount") or "0"))
            except (InvalidOperation, ValueError):
                return StepValidationResult.fail(f"Line {i}: debit and credit must be numbers.")
            if dr < 0 or cr < 0:
                return StepValidationResult.fail(f"Line {i}: amounts cannot be negative.")
            if dr > 0 and cr > 0:
                return StepValidationResult.fail(f"Line {i}: a line is either a debit or a credit, not both.")
            if dr == 0 and cr == 0:
                return StepValidationResult.fail(f"Line {i}: enter a debit or credit amount.")
            dr_total += dr
            cr_total += cr
        if dr_total != cr_total:
            return StepValidationResult.fail(
                f"Debits ({dr_total:.2f}) must equal credits ({cr_total:.2f})."
            )
        if dr_total == 0:
            return StepValidationResult.fail("Total cannot be zero.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        lines = state.get(K.KEY_LINES) or []
        valid = [ln for ln in lines if ln.get("account_id")]
        if not valid:
            return None
        dr_total = Decimal(0)
        for ln in valid:
            try:
                dr_total += Decimal(str(ln.get("debit_amount") or "0"))
            except (InvalidOperation, ValueError):
                continue
        return f"{len(valid)} line(s) \u00b7 total {dr_total:.2f}"
