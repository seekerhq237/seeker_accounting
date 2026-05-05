from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

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

    def _build_preview_table(self) -> DataTable:
        model = QStandardItemModel(0, 3, self)
        model.setHorizontalHeaderLabels(["Ref", "Line", "Amount"])

        table = DataTable(
            columns=(
                DataTableColumn(key="ref", title="Ref"),
                DataTableColumn(key="line", title="Line"),
                DataTableColumn(key="amount", title="Amount"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=self,
        )
        table.set_model(model)
        table.view().setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.view().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.view().verticalHeader().setVisible(False)
        table.view().verticalHeader().setDefaultSectionSize(28)
        table.view().setShowGrid(False)
        table.view().setAlternatingRowColors(False)
        table.setStyleSheet(f"background: {self._template_dto.statement_background};")
        table.view().setColumnWidth(0, 100)
        table.view().setColumnWidth(1, 560)
        table.view().setColumnWidth(2, 180)

        rows = self._build_rows()
        for row_index, row in enumerate(rows):
            self._bind_row(model, row)
            table.view().setRowHeight(row_index, self._template_dto.row_height)
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
        model: QStandardItemModel,
        row_data: "tuple[str, str | None, str, Decimal | None]",
    ) -> None:
        row_type, ref, label, amount = row_data
        ref_item = self._make_item(ref or "")
        label_item = self._make_item(label)
        amount_item = self._make_item("" if amount is None else self._fmt(amount))
        amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if row_type == "section":
            self._apply_row_style(ref_item, label_item, amount_item, True, self._template_dto.section_background)
        elif row_type == "subtotal":
            self._apply_row_style(ref_item, label_item, amount_item, True, self._template_dto.subtotal_background)
        else:
            self._apply_row_style(ref_item, label_item, amount_item, False, self._template_dto.statement_background)

        model.appendRow([ref_item, label_item, amount_item])

    def _apply_row_style(
        self,
        ref_item: QStandardItem,
        label_item: QStandardItem,
        amount_item: QStandardItem,
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
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

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

