from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.insight_card_dto import InsightDetailDTO
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


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

        table = QTableWidget(wrapper)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        configure_compact_table(table)
        table.setRowCount(len(self._detail_dto.card.numeric_basis))
        table.cellDoubleClicked.connect(self._on_basis_double_clicked)
        for row_index, item in enumerate(self._detail_dto.card.numeric_basis):
            label_item = QTableWidgetItem(item.label)
            if item.detail_key:
                label_item.setData(Qt.ItemDataRole.UserRole, item.detail_key)
            table.setItem(row_index, 0, label_item)
            table.setItem(row_index, 1, QTableWidgetItem(item.value_text))
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

        table = QTableWidget(wrapper)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Ratio", "Current", "Prior"])
        configure_compact_table(table)
        table.setRowCount(len(self._detail_dto.related_ratios))
        table.cellDoubleClicked.connect(self._on_ratio_double_clicked)
        for row_index, ratio in enumerate(self._detail_dto.related_ratios):
            label_item = QTableWidgetItem(ratio.label)
            if ratio.detail_key:
                label_item.setData(Qt.ItemDataRole.UserRole, ratio.detail_key)
            table.setItem(row_index, 0, label_item)
            table.setItem(row_index, 1, QTableWidgetItem(ratio.display_value))
            table.setItem(row_index, 2, QTableWidgetItem(ratio.prior_display_value or ""))
        layout.addWidget(table, 1)
        self._ratio_table = table
        return wrapper

    def _on_basis_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        self._open_from_table(self._basis_table, row)

    def _on_ratio_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        self._open_from_table(self._ratio_table, row)

    def _open_from_table(self, table: QTableWidget, row: int) -> None:
        if self._detail_opener is None:
            return
        item = table.item(row, 0)
        if item is None:
            return
        detail_key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(detail_key, str) and detail_key:
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
