"""Step 2 — Lines: revaluation table (account, current book, target)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.fx_revaluation import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_HEADERS = ("Account", "Current book", "Target", "Description")


class LinesStep(WizardStep):
    key = "lines"
    title = "Revaluation lines"
    subtitle = (
        "Add one row per FX-denominated account. Enter its current local-currency "
        "book amount and the new target amount after revaluation."
    )

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._account_options: list[tuple[int, str]] = []
        self._loaded = False

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._table = QTableWidget(0, len(_HEADERS), root)
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self._table, 1)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Add row", root)
        add_btn.clicked.connect(self._add_row)
        remove_btn = QPushButton("Remove selected", root)
        remove_btn.clicked.connect(self._remove_selected)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addStretch(1)
        outer.addLayout(buttons)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if not self._loaded:
            self._populate_account_options(context)
            self._loaded = True
        if self._table is None:
            return
        existing = state.get(K.KEY_LINES) or ()
        self._table.setRowCount(0)
        for entry in existing:
            self._add_row(prefill=entry)
        if self._table.rowCount() == 0:
            self._add_row()

    def _populate_account_options(self, context: WizardContext) -> None:
        company_id = context.require_company_id()
        try:
            options = context.service_registry.chart_of_accounts_service.list_account_lookup_options(
                company_id, active_only=True
            )
        except Exception:
            options = []
        self._account_options = [
            (int(a.id), f"{a.account_code} — {a.account_name}")
            for a in options
            if a.is_active and a.allow_manual_posting
        ]

    def _add_row(self, *, prefill: dict | None = None) -> None:
        if self._table is None:
            return
        row = self._table.rowCount()
        self._table.insertRow(row)

        combo = QComboBox(self._table)
        combo.addItem("(select account)", None)
        for account_id, label in self._account_options:
            combo.addItem(label, account_id)
        if prefill is not None and isinstance(prefill.get("account_id"), int):
            idx = combo.findData(prefill["account_id"])
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self._table.setCellWidget(row, 0, combo)

        current_edit = QLineEdit(self._table)
        if prefill is not None and prefill.get("current_book_amount") is not None:
            current_edit.setText(str(prefill["current_book_amount"]))
        else:
            current_edit.setText("0")
        self._table.setCellWidget(row, 1, current_edit)

        target_edit = QLineEdit(self._table)
        if prefill is not None and prefill.get("target_amount") is not None:
            target_edit.setText(str(prefill["target_amount"]))
        else:
            target_edit.setText("0")
        self._table.setCellWidget(row, 2, target_edit)

        desc_edit = QLineEdit(self._table)
        if prefill is not None and prefill.get("description"):
            desc_edit.setText(str(prefill["description"]))
        self._table.setCellWidget(row, 3, desc_edit)

    def _remove_selected(self) -> None:
        if self._table is None:
            return
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)

    def write_back(self, state: WizardState) -> None:
        if self._table is None:
            return
        rows: list[dict] = []
        for r in range(self._table.rowCount()):
            combo = self._table.cellWidget(r, 0)
            current = self._table.cellWidget(r, 1)
            target = self._table.cellWidget(r, 2)
            desc = self._table.cellWidget(r, 3)
            account_id = combo.currentData() if isinstance(combo, QComboBox) else None
            current_str = current.text().strip() if isinstance(current, QLineEdit) else ""
            target_str = target.text().strip() if isinstance(target, QLineEdit) else ""
            description = desc.text().strip() if isinstance(desc, QLineEdit) else ""
            rows.append(
                {
                    "account_id": int(account_id) if isinstance(account_id, int) else None,
                    "current_book_amount": current_str,
                    "target_amount": target_str,
                    "description": description or None,
                }
            )
        state[K.KEY_LINES] = tuple(rows)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        rows = state.get(K.KEY_LINES) or ()
        if not rows:
            return StepValidationResult.fail("Add at least one revaluation line.")
        any_nonzero = False
        seen: set[int] = set()
        for i, row in enumerate(rows, start=1):
            if not isinstance(row.get("account_id"), int):
                return StepValidationResult.fail(f"Row {i}: pick an account.")
            if row["account_id"] in seen:
                return StepValidationResult.fail(
                    f"Row {i}: account is duplicated. Each account may appear only once."
                )
            seen.add(row["account_id"])
            try:
                cur = Decimal(str(row.get("current_book_amount") or "0"))
                tgt = Decimal(str(row.get("target_amount") or "0"))
            except (InvalidOperation, ValueError):
                return StepValidationResult.fail(
                    f"Row {i}: current and target amounts must be valid numbers."
                )
            if (tgt - cur) != Decimal("0"):
                any_nonzero = True
        if not any_nonzero:
            return StepValidationResult.fail(
                "All rows have zero adjustment. Add at least one row where target ≠ current."
            )
        return StepValidationResult.ok()
