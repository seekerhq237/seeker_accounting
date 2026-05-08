"""Step 2 — Review computed payslips before approval."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.wizards.payroll_run import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.components import (
    DataTable,
    DataTableColumn,
    apply_status_chip_to_column,
)


_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="employee_number", title="Employee #", min_width=110),
    DataTableColumn(key="name", title="Name", min_width=220),
    DataTableColumn(key="status", title="Status", min_width=120),
    DataTableColumn(key="gross", title="Gross", is_numeric=True, min_width=120),
    DataTableColumn(key="net", title="Net", is_numeric=True, min_width=120),
)


class ReviewEmployeesStep(WizardStep):
    key = "review_employees"
    title = "Review Employees"
    subtitle = "Inspect computed totals before approving."

    def __init__(self) -> None:
        super().__init__()
        self._table: DataTable | None = None
        self._model: QStandardItemModel | None = None
        self._status_delegate = None
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
        outer.setSpacing(8)

        intro = QLabel(
            "These totals reflect the most recent calculation. Use the Payroll "
            "module's run editor to exclude individual employees before "
            "returning here to approve.",
            root,
        )
        intro.setWordWrap(True)
        intro.setObjectName("WizardMutedText")
        outer.addWidget(intro)

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
        self._status_delegate = apply_status_chip_to_column(
            self._table.view(), 2
        )
        outer.addWidget(self._table, 1)

        self._summary = QLabel("", root)
        self._summary.setObjectName("WizardBodyTextStrong")
        outer.addWidget(self._summary)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        if self._model is None or self._summary is None:
            return
        run_id = state.get(K.KEY_RUN_ID)
        if not isinstance(run_id, int):
            self._summary.setText("No run is loaded.")
            return
        company_id = context.require_company_id()
        service = context.service_registry.payroll_run_service
        rows = service.list_run_employees(company_id, run_id)

        included = [r for r in rows if r.status_code != "excluded"]
        gross_total = sum((r.gross_earnings for r in included), Decimal("0"))
        net_total = sum((r.net_payable for r in included), Decimal("0"))

        self._model.removeRows(0, self._model.rowCount())
        for row in rows:
            self._model.appendRow([
                self._make_item(row.employee_number),
                self._make_item(row.employee_display_name),
                self._make_item(row.status_code),
                self._make_numeric(row.gross_earnings),
                self._make_numeric(row.net_payable),
            ])

        currency = state.get(K.KEY_CURRENCY_CODE) or ""
        self._summary.setText(
            f"{len(included)} included / {len(rows)} total  ·  "
            f"Gross: {gross_total:,.2f} {currency}  ·  Net: {net_total:,.2f} {currency}"
        )

        state[K.KEY_EMPLOYEE_COUNT] = len(included)
        state[K.KEY_TOTAL_GROSS] = str(gross_total)
        state[K.KEY_TOTAL_NET] = str(net_total)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not state.get(K.KEY_EMPLOYEE_COUNT):
            return StepValidationResult.fail("No included employees in this run.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        n = state.get(K.KEY_EMPLOYEE_COUNT, 0)
        net = state.get(K.KEY_TOTAL_NET) or "0"
        cur = state.get(K.KEY_CURRENCY_CODE) or ""
        return f"{n} employee(s) included; net payable {net} {cur}."
