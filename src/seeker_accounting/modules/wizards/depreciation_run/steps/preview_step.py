"""Step 2 — Preview per-asset depreciation lines."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.wizards.depreciation_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="asset_number", title="Asset #", min_width=100),
    DataTableColumn(key="asset_name", title="Asset", min_width=200),
    DataTableColumn(key="depreciation", title="Depreciation", is_numeric=True, min_width=120),
    DataTableColumn(key="accumulated", title="Accum. After", is_numeric=True, min_width=120),
    DataTableColumn(key="nbv", title="NBV After", is_numeric=True, min_width=120),
)


class PreviewStep(WizardStep):
    key = "preview"
    title = "Preview"
    subtitle = "Review the per-asset depreciation lines before posting."

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._table: DataTable | None = None
        self._model: QStandardItemModel | None = None

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
        outer.setSpacing(8)

        self._summary = QLabel("", root)
        self._summary.setObjectName("WizardBodyTextStrong")
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
        run_id = state.get(K.KEY_RUN_ID)
        if not isinstance(run_id, int):
            self._summary.setText("No run loaded.")
            return
        company_id = context.require_company_id()
        run = context.service_registry.depreciation_run_service.get_depreciation_run(
            company_id, run_id
        )
        self._summary.setText(
            f"Run {run.run_number or '(draft)'}  \u00b7  {run.asset_count} asset(s)  "
            f"\u00b7  Total: {run.total_depreciation:,.2f}"
        )
        self._model.removeRows(0, self._model.rowCount())
        for line in run.lines:
            self._model.appendRow([
                self._make_item(line.asset_number),
                self._make_item(line.asset_name),
                self._make_numeric(line.depreciation_amount),
                self._make_numeric(line.accumulated_depreciation_after),
                self._make_numeric(line.net_book_value_after),
            ])
        state[K.KEY_ASSET_COUNT] = run.asset_count
        state[K.KEY_TOTAL_DEPRECIATION] = str(run.total_depreciation)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_ASSET_COUNT):
            return StepValidationResult.fail("Run has no eligible assets.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        n = state.get(K.KEY_ASSET_COUNT, 0)
        total = state.get(K.KEY_TOTAL_DEPRECIATION) or "0"
        return f"{n} asset(s); total depreciation {total}."
