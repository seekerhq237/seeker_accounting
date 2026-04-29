"""Step 2 — Preview per-asset depreciation lines."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.depreciation_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class PreviewStep(WizardStep):
    key = "preview"
    title = "Preview"
    subtitle = "Review the per-asset depreciation lines before posting."

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._table: QTableWidget | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._summary = QLabel("", root)
        self._summary.setStyleSheet("color: #2E3848; font-size: 12px; font-weight: 600;")
        outer.addWidget(self._summary)

        self._table = QTableWidget(0, 5, root)
        self._table.setHorizontalHeaderLabels(
            ["Asset #", "Asset", "Depreciation", "Accum. After", "NBV After"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self._table, 1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._table is None or self._summary is None:
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
        self._table.setRowCount(len(run.lines))
        for i, line in enumerate(run.lines):
            self._table.setItem(i, 0, QTableWidgetItem(line.asset_number))
            self._table.setItem(i, 1, QTableWidgetItem(line.asset_name))
            for col, value in (
                (2, line.depreciation_amount),
                (3, line.accumulated_depreciation_after),
                (4, line.net_book_value_after),
            ):
                item = QTableWidgetItem(f"{value:,.2f}")
                item.setTextAlignment(0x0002 | 0x0080)
                self._table.setItem(i, col, item)
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
