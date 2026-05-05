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

from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioDetailDTO
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn


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

        self._table = DataTable(
            columns=(
                DataTableColumn(key="component", title="Component"),
                DataTableColumn(key="source", title="Source"),
                DataTableColumn(key="amount", title="Amount"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=self,
        )
        self._model = QStandardItemModel(0, 3, self)
        self._model.setHorizontalHeaderLabels(["Component", "Source", "Amount"])
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
        self._model.removeRows(0, self._model.rowCount())
        for component in self._detail_dto.components:
            label_item = self._make_item(component.label)
            if component.detail_key:
                label_item.setData(component.detail_key, Qt.ItemDataRole.UserRole)
            amount_item = self._make_item("" if component.amount is None else f"{component.amount:,.2f}")
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._model.appendRow([
                label_item,
                self._make_item(component.source_label),
                amount_item,
            ])

    def _on_row_double_clicked(self, index) -> None:
        if self._detail_opener is None:
            return
        proxy = self._table.view().model()
        if proxy is None:
            return
        src = proxy.mapToSource(index)
        row = src.row()
        item = self._model.item(row, 0)
        if item is None:
            return
        detail_key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(detail_key, str) and detail_key:
            self._detail_opener(detail_key)

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @classmethod
    def open(
        cls,
        detail_dto: RatioDetailDTO,
        detail_opener: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(detail_dto, detail_opener=detail_opener, parent=parent)
        dialog.exec()
