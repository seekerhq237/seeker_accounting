from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.ias_income_statement_dto import (
    IasIncomeStatementReportDTO,
)
from seeker_accounting.modules.reporting.dto.ias_income_statement_template_dto import (
    IasIncomeStatementTemplateDTO,
)

_ZERO = Decimal("0.00")


class IasIncomeStatementTemplatePreviewDialog(QDialog):
    """Presentation preview for the IAS/IFRS income statement templates."""

    def __init__(
        self,
        template_dto: IasIncomeStatementTemplateDTO,
        report_dto: IasIncomeStatementReportDTO | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._template_dto = template_dto
        self._report_dto = report_dto

        self.setWindowTitle(f"Template Preview - {template_dto.template_title}")
        self.setMinimumSize(900, 660)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 14)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_preview_table(), 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        title = QLabel(self._template_dto.template_title, card)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        badge = QLabel(self._template_dto.standard_note, card)
        badge.setProperty("chipTone", "info")
        layout.addWidget(badge)

        description = QLabel(self._template_dto.description, card)
        description.setObjectName("PageSummary")
        description.setWordWrap(True)
        layout.addWidget(description)
        return card

    def _build_preview_table(self) -> QWidget:
        table = QTableWidget(self)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Ref", "Line", "Amount"])
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(28)
        table.setWordWrap(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setStyleSheet(f"background: {self._template_dto.statement_background};")
        table.setColumnWidth(0, 100)
        table.setColumnWidth(1, 560)
        table.setColumnWidth(2, 180)

        rows = self._build_rows()
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self._bind_row(table, row_index, row)
            table.setRowHeight(row_index, self._template_dto.row_height)
        return table

    def _build_rows(self) -> list[tuple[str, str | None, str, Decimal | None]]:
        if self._report_dto is None:
            return [("section", None, "No report loaded for preview", None)]

        rows: list[tuple[str, str | None, str, Decimal | None]] = []
        for line in self._report_dto.lines:
            label = f"{'    ' * line.indent_level}{line.label}"
            row_type = "section" if line.row_kind_code == "group" else ("subtotal" if line.is_formula else "line")
            rows.append((row_type, None if row_type == "section" else line.code, label, line.signed_amount))
        return rows

    def _bind_row(
        self,
        table: QTableWidget,
        row_index: int,
        row_data: tuple[str, str | None, str, Decimal | None],
    ) -> None:
        row_type, ref, label, amount = row_data
        ref_item = QTableWidgetItem(ref or "")
        label_item = QTableWidgetItem(label)
        amount_item = QTableWidgetItem("" if amount is None else self._fmt(amount))
        amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if row_type == "section":
            self._apply_row_style(ref_item, label_item, amount_item, True, self._template_dto.section_background)
        elif row_type == "subtotal":
            self._apply_row_style(ref_item, label_item, amount_item, True, self._template_dto.subtotal_background)
        else:
            self._apply_row_style(ref_item, label_item, amount_item, False, self._template_dto.statement_background)

        table.setItem(row_index, 0, ref_item)
        table.setItem(row_index, 1, label_item)
        table.setItem(row_index, 2, amount_item)

    def _apply_row_style(
        self,
        ref_item: QTableWidgetItem,
        label_item: QTableWidgetItem,
        amount_item: QTableWidgetItem,
        bold: bool,
        color_hex: str,
    ) -> None:
        background = QColor(color_hex)
        for item in (ref_item, label_item, amount_item):
            item.setBackground(background)
            font = item.font()
            font.setBold(bold)
            item.setFont(font)

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"

    @classmethod
    def show_preview(
        cls,
        template_dto: IasIncomeStatementTemplateDTO,
        report_dto: IasIncomeStatementReportDTO | None,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(template_dto, report_dto, parent)
        dialog.exec()

