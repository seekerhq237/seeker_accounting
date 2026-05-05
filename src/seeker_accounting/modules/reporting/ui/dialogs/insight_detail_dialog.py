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

from seeker_accounting.modules.reporting.dto.insight_card_dto import InsightDetailDTO
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


class InsightDetailDialog(QDialog):
    """Expanded management-insight dialog with traceable numeric basis."""

    def __init__(
        self,
        detail_dto: InsightDetailDTO,
        detail_opener: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._detail_dto = detail_dto
        self._detail_opener = detail_opener
        self.setWindowTitle(detail_dto.card.title)
        self.setMinimumSize(860, 620)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_basis_table(), 1)
        layout.addWidget(self._build_related_table(), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(16, 14, 16, 12)
        inner.setSpacing(6)

        title = QLabel(self._detail_dto.card.title, card)
        title.setObjectName("InfoCardTitle")
        inner.addWidget(title)

        period = QLabel(f"Period: {self._detail_dto.period_label}", card)
        period.setObjectName("PageSummary")
        inner.addWidget(period)

        statement = QLabel(self._detail_dto.card.statement, card)
        statement.setObjectName("AnalysisInsightBody")
        statement.setWordWrap(True)
        inner.addWidget(statement)

        why = QLabel(self._detail_dto.card.why_it_matters, card)
        why.setObjectName("AnalysisInsightMeta")
        why.setWordWrap(True)
        inner.addWidget(why)

        if self._detail_dto.card.comparison_text:
            comparison = QLabel(self._detail_dto.card.comparison_text, card)
            comparison.setObjectName("AnalysisInsightMeta")
            comparison.setWordWrap(True)
            inner.addWidget(comparison)

        if self._detail_dto.limitations:
            limit = QLabel("Limitations: " + " | ".join(self._detail_dto.limitations[:3]), card)
            limit.setObjectName("AnalysisInsightMeta")
            limit.setWordWrap(True)
            inner.addWidget(limit)
        return card

    def _build_basis_table(self) -> QWidget:
        wrapper = QFrame(self)
        wrapper.setObjectName("PageCard")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("Numeric Basis", wrapper)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        self._basis_model = QStandardItemModel(0, 2, wrapper)
        self._basis_model.setHorizontalHeaderLabels(["Metric", "Value"])
        self._basis_model.setRowCount(len(self._detail_dto.card.numeric_basis))
        for row_index, nb_item in enumerate(self._detail_dto.card.numeric_basis):
            label_item = QStandardItem(nb_item.label)
            label_item.setEditable(False)
            if nb_item.detail_key:
                label_item.setData(nb_item.detail_key, Qt.ItemDataRole.UserRole)
            self._basis_model.setItem(row_index, 0, label_item)
            val_item = QStandardItem(nb_item.value_text)
            val_item.setEditable(False)
            self._basis_model.setItem(row_index, 1, val_item)
        table = DataTable(
            columns=(
                DataTableColumn(key="metric", title="Metric"),
                DataTableColumn(key="value", title="Value"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=wrapper,
        )
        table.set_model(self._basis_model)
        table.view().doubleClicked.connect(self._on_basis_double_clicked)
        layout.addWidget(table, 1)
        self._basis_table = table
        return wrapper

    def _build_related_table(self) -> QWidget:
        wrapper = QFrame(self)
        wrapper.setObjectName("PageCard")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("Related Ratios", wrapper)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        self._ratio_model = QStandardItemModel(0, 3, wrapper)
        self._ratio_model.setHorizontalHeaderLabels(["Ratio", "Current", "Prior"])
        self._ratio_model.setRowCount(len(self._detail_dto.related_ratios))
        for row_index, ratio in enumerate(self._detail_dto.related_ratios):
            label_item = QStandardItem(ratio.label)
            label_item.setEditable(False)
            if ratio.detail_key:
                label_item.setData(ratio.detail_key, Qt.ItemDataRole.UserRole)
            self._ratio_model.setItem(row_index, 0, label_item)
            cur_item = QStandardItem(ratio.display_value)
            cur_item.setEditable(False)
            self._ratio_model.setItem(row_index, 1, cur_item)
            prior_item = QStandardItem(ratio.prior_display_value or "")
            prior_item.setEditable(False)
            self._ratio_model.setItem(row_index, 2, prior_item)
        table = DataTable(
            columns=(
                DataTableColumn(key="ratio", title="Ratio"),
                DataTableColumn(key="current", title="Current"),
                DataTableColumn(key="prior", title="Prior"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=wrapper,
        )
        table.set_model(self._ratio_model)
        table.view().doubleClicked.connect(self._on_ratio_double_clicked)
        layout.addWidget(table, 1)
        self._ratio_table = table
        return wrapper

    def _on_basis_double_clicked(self, index) -> None:
        proxy = self._basis_table.view().model()
        if proxy is None:
            return
        src = proxy.mapToSource(index)
        item = self._basis_model.item(src.row(), 0)
        if item is None:
            return
        detail_key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(detail_key, str) and detail_key and self._detail_opener is not None:
            self._detail_opener(detail_key)

    def _on_ratio_double_clicked(self, index) -> None:
        proxy = self._ratio_table.view().model()
        if proxy is None:
            return
        src = proxy.mapToSource(index)
        item = self._ratio_model.item(src.row(), 0)
        if item is None:
            return
        detail_key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(detail_key, str) and detail_key and self._detail_opener is not None:
            self._detail_opener(detail_key)

    @classmethod
    def open(
        cls,
        detail_dto: InsightDetailDTO,
        detail_opener: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(detail_dto, detail_opener=detail_opener, parent=parent)
        dialog.exec()
