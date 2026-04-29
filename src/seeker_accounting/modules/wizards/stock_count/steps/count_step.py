"""Step 2 — Counts: enter counted quantity per stock item."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.stock_count import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


_HEADERS = ("Code", "Item", "UoM", "System qty", "Counted qty", "Avg cost")


class CountStep(WizardStep):
    key = "count"
    title = "Enter counts"
    subtitle = "For each item, enter the physically counted quantity. Leave blank to skip."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._row_meta: list[dict] = []
        self._loaded = False

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        info = QLabel(
            "<i>Tip:</i> if an item's counted qty is left blank, no adjustment is "
            "proposed for it. Enter <b>0</b> explicitly to record a stock-out.",
            root,
        )
        info.setWordWrap(True)
        outer.addWidget(info)

        self._table = QTableWidget(0, len(_HEADERS), root)
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self._table, 1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._loaded:
            return
        self._populate(context, state)
        self._loaded = True

    def _populate(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None:
            return
        company_id = context.require_company_id()
        try:
            positions = context.service_registry.inventory_valuation_service.list_stock_positions(
                company_id
            )
        except Exception:
            positions = []
        self._table.setRowCount(0)
        self._row_meta = []
        existing_counts = {}
        for entry in (state.get(K.KEY_COUNTS) or ()):
            iid = entry.get("item_id")
            if isinstance(iid, int):
                existing_counts[iid] = entry.get("counted_qty")
        for pos in positions:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, _ro(pos.item_code))
            self._table.setItem(row, 1, _ro(pos.item_name))
            self._table.setItem(row, 2, _ro(pos.unit_of_measure_code or ""))
            self._table.setItem(row, 3, _ro_num(pos.quantity_on_hand))
            count_edit = QLineEdit(self._table)
            existing = existing_counts.get(int(pos.item_id))
            if existing is not None and existing != "":
                count_edit.setText(str(existing))
            self._table.setCellWidget(row, 4, count_edit)
            avg_cost = pos.weighted_average_cost or Decimal("0")
            self._table.setItem(row, 5, _ro_num(avg_cost))
            self._row_meta.append(
                {
                    "item_id": int(pos.item_id),
                    "item_code": pos.item_code,
                    "item_name": pos.item_name,
                    "system_qty": pos.quantity_on_hand,
                    "avg_cost": avg_cost,
                }
            )

    def write_back(self, state: WizardState) -> None:
        if self._table is None:
            return
        rows: list[dict] = []
        for r in range(self._table.rowCount()):
            edit = self._table.cellWidget(r, 4)
            text = edit.text().strip() if isinstance(edit, QLineEdit) else ""
            meta = self._row_meta[r]
            rows.append(
                {
                    **meta,
                    "counted_qty": text,
                }
            )
        state[K.KEY_COUNTS] = tuple(rows)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        rows = state.get(K.KEY_COUNTS) or ()
        any_count = False
        for i, row in enumerate(rows, start=1):
            text = (row.get("counted_qty") or "").strip()
            if not text:
                continue
            try:
                Decimal(text)
            except (InvalidOperation, ValueError):
                return StepValidationResult.fail(
                    f"Row {i} ({row.get('item_code')}): counted qty must be a number."
                )
            any_count = True
        if not any_count:
            return StepValidationResult.fail(
                "Enter at least one counted quantity, otherwise there is nothing to adjust."
            )
        return StepValidationResult.ok()


def _ro(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _ro_num(value: Decimal) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
    return item
