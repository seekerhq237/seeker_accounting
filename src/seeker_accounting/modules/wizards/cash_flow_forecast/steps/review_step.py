"""Step 2 — Review: shows the projected cash flow per bucket."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from seeker_accounting.modules.reporting.dto.cash_flow_forecast_dto import (
    CashFlowBucketUnit,
    CashFlowForecastDTO,
)
from seeker_accounting.modules.wizards.cash_flow_forecast import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


_COLUMNS: tuple[DataTableColumn, ...] = (
    DataTableColumn(key="period", title="Period", min_width=120),
    DataTableColumn(key="opening", title="Opening", is_numeric=True, min_width=110),
    DataTableColumn(key="receipts", title="Receipts", is_numeric=True, min_width=110),
    DataTableColumn(key="payments", title="Payments", is_numeric=True, min_width=110),
    DataTableColumn(key="net", title="Net", is_numeric=True, min_width=110),
    DataTableColumn(key="closing", title="Closing", is_numeric=True, min_width=110),
    DataTableColumn(key="docs", title="Docs (R / P)", min_width=110),
)


class ReviewStep(WizardStep):
    key = "review"
    title = "Cash flow projection"
    subtitle = "Read-only forecast based on posted balances and open AR/AP documents."

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._table: DataTable | None = None
        self._model: QStandardItemModel | None = None
        self._warnings: QLabel | None = None

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

        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
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

        self._warnings = QLabel(root)
        self._warnings.setWordWrap(True)
        self._warnings.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._warnings)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        as_of = state.get(K.KEY_AS_OF_DATE)
        if not isinstance(as_of, date):
            return
        unit_value = state.get(K.KEY_BUCKET_UNIT) or CashFlowBucketUnit.WEEK.value
        try:
            unit = CashFlowBucketUnit(str(unit_value))
        except ValueError:
            unit = CashFlowBucketUnit.WEEK
        count = state.get(K.KEY_BUCKET_COUNT)
        if not isinstance(count, int):
            count = 8

        forecast = context.service_registry.cash_flow_forecast_service.forecast(
            company_id,
            as_of,
            bucket_unit=unit,
            bucket_count=count,
            include_ar=bool(state.get(K.KEY_INCLUDE_AR, True)),
            include_ap=bool(state.get(K.KEY_INCLUDE_AP, True)),
        )
        state[K.KEY_FORECAST] = forecast
        self._render(forecast)

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        return StepValidationResult.ok()

    def _render(self, forecast: CashFlowForecastDTO) -> None:
        if self._summary is not None:
            self._summary.setText(
                f"<b>As-of:</b> {forecast.as_of_date.isoformat()} · "
                f"<b>Buckets:</b> {forecast.bucket_count} {forecast.bucket_unit.value.lower()}(s) · "
                f"<b>Cash accounts:</b> {forecast.cash_account_count}<br>"
                f"<b>Opening cash:</b> {_fmt(forecast.opening_cash_balance)} · "
                f"<b>Total receipts:</b> {_fmt(forecast.total_expected_receipts)} · "
                f"<b>Total payments:</b> {_fmt(forecast.total_expected_payments)} · "
                f"<b>Closing cash:</b> {_fmt(forecast.closing_cash_balance)}"
            )
        if self._model is not None:
            self._model.removeRows(0, self._model.rowCount())
            for b in forecast.buckets:
                row = [
                    self._make_item(b.label),
                    self._make_numeric(b.opening_balance),
                    self._make_numeric(b.expected_receipts),
                    self._make_numeric(b.expected_payments),
                    self._make_numeric(b.net_movement),
                    self._make_numeric(b.closing_balance),
                    self._make_item(
                        f"{b.receipts_document_count} / {b.payments_document_count}"
                    ),
                ]
                if b.closing_balance < Decimal("0"):
                    row[5].setForeground(QBrush(Qt.GlobalColor.red))
                self._model.appendRow(row)
        if self._warnings is not None:
            extras: list[str] = list(forecast.warnings)
            if forecast.out_of_range_receipts > Decimal("0") or \
                    forecast.out_of_range_payments > Decimal("0"):
                extras.append(
                    f"Beyond horizon: receipts {_fmt(forecast.out_of_range_receipts)}, "
                    f"payments {_fmt(forecast.out_of_range_payments)}."
                )
            if forecast.undated_receipts > Decimal("0") or \
                    forecast.undated_payments > Decimal("0"):
                extras.append(
                    f"Undated documents: receipts {_fmt(forecast.undated_receipts)}, "
                    f"payments {_fmt(forecast.undated_payments)}."
                )
            if extras:
                bullets = "".join(f"<li>{w}</li>" for w in extras)
                self._warnings.setText(
                    f"<b>Notes &amp; warnings</b><ul>{bullets}</ul>"
                )
            else:
                self._warnings.setText("")


def _fmt(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,.2f}"
