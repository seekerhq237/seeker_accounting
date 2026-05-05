"""Step 3 — Variance review (read-only)."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.wizards.stock_count import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="code", title="Code", min_width=110),
    DataTableColumn(key="item", title="Item", min_width=220),
    DataTableColumn(key="system", title="System", is_numeric=True, min_width=100),
    DataTableColumn(key="counted", title="Counted", is_numeric=True, min_width=100),
    DataTableColumn(key="variance", title="Variance", is_numeric=True, min_width=100),
    DataTableColumn(key="cost", title="Cost", is_numeric=True, min_width=110),
    DataTableColumn(key="value_impact", title="Value impact", is_numeric=True, min_width=120),
)


class VarianceReviewStep(WizardStep):
    key = "variance"
    title = "Variance review"
    subtitle = "Only rows with non-zero variance will be posted."

    def __init__(self) -> None:
        super().__init__()
        self._table: DataTable | None = None
        self._model: QStandardItemModel | None = None
        self._summary: QLabel | None = None

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _make_numeric(value) -> QStandardItem:
        text = "" if value is None else f"{Decimal(str(value)):,.2f}"
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return item

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        outer.addWidget(self._summary)

        self._model = QStandardItemModel(0, len(_COLUMNS), root)
        self._model.setHorizontalHeaderLabels([c.title for c in _COLUMNS])
        self._table = DataTable(
            columns=_COLUMNS,
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=root,
        )
        self._table.set_model(self._model)
        outer.addWidget(self._table, 1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._model is None or self._summary is None:
            return
        rows = state.get(K.KEY_COUNTS) or ()
        self._model.removeRows(0, self._model.rowCount())
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
            self._model.appendRow([
                self._make_item(entry.get("item_code") or ""),
                self._make_item(entry.get("item_name") or ""),
                self._make_numeric(system),
                self._make_numeric(counted),
                self._make_numeric(variance),
                self._make_numeric(avg_cost),
                self._make_numeric(value_impact),
            ])
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
