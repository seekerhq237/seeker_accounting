"""Step 3 — Variance review (read-only)."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
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


_HEADERS = ("Code", "Item", "System", "Counted", "Variance", "Cost", "Value impact")


class VarianceReviewStep(WizardStep):
    key = "variance"
    title = "Variance review"
    subtitle = "Only rows with non-zero variance will be posted."

    def __init__(self) -> None:
        super().__init__()
        self._table: QTableWidget | None = None
        self._summary: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        outer.addWidget(self._summary)

        self._table = QTableWidget(0, len(_HEADERS), root)
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3, 4, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self._table, 1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None or self._summary is None:
            return
        rows = state.get(K.KEY_COUNTS) or ()
        self._table.setRowCount(0)
        positive_lines = 0
        negative_lines = 0
        positive_value = Decimal("0")
        negative_value = Decimal("0")
        for entry in rows:
            text = (entry.get("counted_qty") or "").strip()
            if not text:
                continue
            try:
                counted = Decimal(text)
            except Exception:
                continue
            system = Decimal(str(entry.get("system_qty") or "0"))
            variance = counted - system
            if variance == 0:
                continue
            avg_cost = Decimal(str(entry.get("avg_cost") or "0"))
            value_impact = (variance * avg_cost).quantize(Decimal("0.01"))
            if variance > 0:
                positive_lines += 1
                positive_value += value_impact
            else:
                negative_lines += 1
                negative_value += value_impact
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, _ro(str(entry.get("item_code") or "")))
            self._table.setItem(r, 1, _ro(str(entry.get("item_name") or "")))
            self._table.setItem(r, 2, _ro_num(system))
            self._table.setItem(r, 3, _ro_num(counted))
            self._table.setItem(r, 4, _ro_num(variance))
            self._table.setItem(r, 5, _ro_num(avg_cost))
            self._table.setItem(r, 6, _ro_num(value_impact))
        self._summary.setText(
            f"<b>{positive_lines + negative_lines}</b> variance lines  •  "
            f"+{positive_lines} additions ({positive_value})  •  "
            f"−{negative_lines} reductions ({negative_value})"
        )

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        rows = state.get(K.KEY_COUNTS) or ()
        for entry in rows:
            text = (entry.get("counted_qty") or "").strip()
            if not text:
                continue
            try:
                counted = Decimal(text)
                system = Decimal(str(entry.get("system_qty") or "0"))
            except Exception:
                continue
            if counted - system != 0:
                avg_cost = Decimal(str(entry.get("avg_cost") or "0"))
                if counted > system and avg_cost <= 0:
                    return StepValidationResult.fail(
                        f"Item {entry.get('item_code')} has a positive variance but no "
                        "weighted-average cost. Receive stock at a known cost first, or "
                        "remove the count for this item."
                    )
                return StepValidationResult.ok()
        return StepValidationResult.fail(
            "No variances detected — nothing to post. Adjust counts or cancel."
        )


def _ro(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _ro_num(value: Decimal) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
    return item
