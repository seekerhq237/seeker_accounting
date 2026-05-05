from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.trend_analysis_dto import TrendDetailDTO
from seeker_accounting.modules.reporting.ui.widgets.mini_trend_chart import MiniTrendChart
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager


class FinancialAnalysisDetailDialog(QDialog):
    """Trend and variance drilldown for a selected financial-analysis metric."""

    def __init__(
        self,
        theme_manager: ThemeManager,
        detail_dto: TrendDetailDTO,
        detail_opener: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._detail_dto = detail_dto
        self._detail_opener = detail_opener
        self.setWindowTitle(detail_dto.title)
        self.setMinimumSize(860, 620)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)
        layout.addWidget(self._build_header())

        chart_card = QFrame(self)
        chart_card.setObjectName("PageCard")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(14, 12, 14, 12)
        chart_layout.setSpacing(10)
        for series in detail_dto.series:
            title = QLabel(series.label, chart_card)
            title.setObjectName("AnalysisMetricLabel")
            chart_layout.addWidget(title)
            chart = MiniTrendChart(theme_manager, chart_card)
            chart.set_points(series.points, series.color_name)
            chart_layout.addWidget(chart)
        layout.addWidget(chart_card)

        self._table = DataTable(
            columns=(
                DataTableColumn(key="metric", title="Metric"),
                DataTableColumn(key="current", title="Current"),
                DataTableColumn(key="prior", title="Prior"),
                DataTableColumn(key="variance", title="Variance"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=self,
        )
        self._model = QStandardItemModel(0, 4, self)
        self._model.setHorizontalHeaderLabels(["Metric", "Current", "Prior", "Variance"])
        self._table.set_model(self._model)
        self._table.view().doubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._bind_rows()

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(16, 14, 16, 12)
        inner.setSpacing(6)
        title = QLabel(self._detail_dto.title, card)
        title.setObjectName("InfoCardTitle")
        inner.addWidget(title)
        subtitle = QLabel(self._detail_dto.subtitle, card)
        subtitle.setObjectName("PageSummary")
        subtitle.setWordWrap(True)
        inner.addWidget(subtitle)
        return card

    def _bind_rows(self) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for row in self._detail_dto.variance_rows:
            label_item = self._make_item(row.label, user_data=row.detail_key if row.detail_key else None)
            variance_item = self._make_item(self._fmt(row.variance_value))
            variance_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._model.appendRow([
                label_item,
                self._make_item(self._fmt(row.current_value)),
                self._make_item(self._fmt(row.prior_value)),
                variance_item,
            ])

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _on_row_double_clicked(self, index) -> None:
        if self._detail_opener is None:
            return
        proxy = self._table.view().model()
        if proxy is None:
            return
        src = proxy.mapToSource(index)
        row = src.row()
        id_item = self._model.item(row, 0)
        if id_item is None:
            return
        detail_key = id_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(detail_key, str) and detail_key:
            self._detail_opener(detail_key)

    @staticmethod
    def _fmt(value) -> str:
        if value is None:
            return ""
        return f"{value:,.2f}"

    @classmethod
    def open(
        cls,
        theme_manager: ThemeManager,
        detail_dto: TrendDetailDTO,
        detail_opener: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(theme_manager, detail_dto, detail_opener=detail_opener, parent=parent)
        dialog.exec()
