"""Step 2 — Review: shows the projected cash flow per bucket."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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


class ReviewStep(WizardStep):
    key = "review"
    title = "Cash flow projection"
    subtitle = "Read-only forecast based on posted balances and open AR/AP documents."

    def __init__(self) -> None:
        super().__init__()
        self._summary: QLabel | None = None
        self._table: QTableWidget | None = None
        self._warnings: QLabel | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self._summary = QLabel(root)
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._summary)

        self._table = QTableWidget(root)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Period",
            "Opening",
            "Receipts",
            "Payments",
            "Net",
            "Closing",
            "Docs (R / P)",
        ])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
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
        if self._table is not None:
            self._table.setRowCount(len(forecast.buckets))
            for r, b in enumerate(forecast.buckets):
                self._set(r, 0, b.label, align_left=True)
                self._set(r, 1, _fmt(b.opening_balance))
                self._set(r, 2, _fmt(b.expected_receipts))
                self._set(r, 3, _fmt(b.expected_payments))
                self._set(r, 4, _fmt(b.net_movement))
                self._set(r, 5, _fmt(b.closing_balance), highlight_negative=b.closing_balance < Decimal("0"))
                self._set(
                    r,
                    6,
                    f"{b.receipts_document_count} / {b.payments_document_count}",
                )
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

    def _set(
        self,
        row: int,
        col: int,
        text: str,
        *,
        align_left: bool = False,
        highlight_negative: bool = False,
    ) -> None:
        if self._table is None:
            return
        item = QTableWidgetItem(text)
        if align_left:
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if highlight_negative:
            item.setForeground(Qt.GlobalColor.red)
        self._table.setItem(row, col, item)


def _fmt(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,.2f}"
