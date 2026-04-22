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

from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioDetailDTO
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


class RatioDetailDialog(QDialog):
    """Supporting formula and numeric-basis drilldown for a ratio card."""

    def __init__(
        self,
        detail_dto: RatioDetailDTO,
        detail_opener: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._detail_dto = detail_dto
        self._detail_opener = detail_opener
        self.setWindowTitle(detail_dto.title)
        self.setMinimumSize(760, 520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)
        layout.addWidget(self._build_header())

        self._table = QTableWidget(self)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Component", "Source", "Amount"])
        configure_compact_table(self._table)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
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

        formula = QLabel(f"Formula: {self._detail_dto.formula_label}", card)
        formula.setObjectName("AnalysisInsightMeta")
        formula.setWordWrap(True)
        inner.addWidget(formula)

        summary = QLabel(
            f"Value: {self._detail_dto.value_text} | Status: {self._detail_dto.status_label}",
            card,
        )
        summary.setObjectName("AnalysisInsightBody")
        summary.setWordWrap(True)
        inner.addWidget(summary)

        if self._detail_dto.comparison_text:
            comparison = QLabel(self._detail_dto.comparison_text, card)
            comparison.setObjectName("AnalysisInsightMeta")
            comparison.setWordWrap(True)
            inner.addWidget(comparison)

        if self._detail_dto.basis_note:
            note = QLabel(self._detail_dto.basis_note, card)
            note.setObjectName("AnalysisInsightMeta")
            note.setWordWrap(True)
            inner.addWidget(note)

        if self._detail_dto.unavailable_reason:
            unavailable = QLabel(self._detail_dto.unavailable_reason, card)
            unavailable.setObjectName("DialogErrorLabel")
            unavailable.setWordWrap(True)
            inner.addWidget(unavailable)
        return card

    def _bind_rows(self) -> None:
        self._table.setRowCount(len(self._detail_dto.components))
        for row_index, component in enumerate(self._detail_dto.components):
            label_item = QTableWidgetItem(component.label)
            if component.detail_key:
                label_item.setData(Qt.ItemDataRole.UserRole, component.detail_key)
            self._table.setItem(row_index, 0, label_item)
            self._table.setItem(row_index, 1, QTableWidgetItem(component.source_label))
            amount_item = QTableWidgetItem("" if component.amount is None else f"{component.amount:,.2f}")
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_index, 2, amount_item)

    def _on_row_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        if self._detail_opener is None:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        detail_key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(detail_key, str) and detail_key:
            self._detail_opener(detail_key)

    @classmethod
    def open(
        cls,
        detail_dto: RatioDetailDTO,
        detail_opener: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(detail_dto, detail_opener=detail_opener, parent=parent)
        dialog.exec()
