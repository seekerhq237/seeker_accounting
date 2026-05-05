from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.reporting.dto.balance_sheet_template_dto import (
    BalanceSheetTemplateDTO,
)
from seeker_accounting.modules.reporting.dto.ias_balance_sheet_dto import (
    IasBalanceSheetLineDTO,
    IasBalanceSheetReportDTO,
)
from seeker_accounting.modules.reporting.dto.ohada_balance_sheet_dto import (
    OhadaBalanceSheetLineDTO,
    OhadaBalanceSheetReportDTO,
)
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

_ZERO = Decimal("0.00")


class BalanceSheetTemplatePreviewDialog(QDialog):
    """Presentation preview for balance-sheet templates."""

    def __init__(
        self,
        template_dto: BalanceSheetTemplateDTO,
        report_dto: OhadaBalanceSheetReportDTO | IasBalanceSheetReportDTO | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._template_dto = template_dto
        self._report_dto = report_dto

        self.setWindowTitle(f"Template Preview - {template_dto.template_title}")
        self.setMinimumSize(980, 700)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 14)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_style_summary())
        layout.addWidget(self._build_preview_canvas(), 1)

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

    def _build_style_summary(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        for label, value in (
            ("Row Height", str(self._template_dto.row_height)),
            ("Label Font", f"{self._template_dto.label_font_size} pt"),
            ("Amount Font", f"{self._template_dto.amount_font_size} pt"),
        ):
            layout.addWidget(self._build_metric(label, value))

        for label, color_hex in (
            ("Section", self._template_dto.section_background),
            ("Subtotal", self._template_dto.subtotal_background),
            ("Statement", self._template_dto.statement_background),
        ):
            layout.addWidget(self._build_color_swatch(label, color_hex))
        layout.addStretch(1)
        return card

    def _build_metric(self, label_text: str, value_text: str) -> QWidget:
        card = QWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        label = QLabel(label_text, card)
        label.setProperty("role", "caption")
        layout.addWidget(label)

        value = QLabel(value_text, card)
        value.setObjectName("TopBarValue")
        layout.addWidget(value)
        return card

    def _build_color_swatch(self, label_text: str, color_hex: str) -> QWidget:
        card = QWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(label_text, card)
        label.setProperty("role", "caption")
        layout.addWidget(label)

        swatch = QFrame(card)
        swatch.setFixedSize(84, 28)
        swatch.setStyleSheet(
            f"background-color: {color_hex}; border: 1px solid #CBD5E1; border-radius: 6px;"
        )
        layout.addWidget(swatch)

        code = QLabel(color_hex.upper(), card)
        code.setProperty("role", "caption")
        layout.addWidget(code)
        return card

    def _build_preview_canvas(self) -> QWidget:
        if isinstance(self._report_dto, OhadaBalanceSheetReportDTO):
            return self._build_ohada_preview(self._report_dto)
        if isinstance(self._report_dto, IasBalanceSheetReportDTO):
            return self._build_ias_preview(self._report_dto)
        return self._build_fallback_preview()

    def _build_ohada_preview(self, report_dto: OhadaBalanceSheetReportDTO) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("PageCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("OHADA Balance Sheet Preview", panel)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal, panel)
        splitter.addWidget(
            self._build_ohada_table(
                title="Assets",
                lines=report_dto.asset_lines or self._fallback_ohada_asset_lines(),
                headers=("Ref", "Line", "Gross", "Deprec./Prov.", "Net"),
                is_assets=True,
            )
        )
        splitter.addWidget(
            self._build_ohada_table(
                title="Liabilities and Equity",
                lines=report_dto.liability_lines or self._fallback_ohada_liability_lines(),
                headers=("Ref", "Line", "Amount"),
                is_assets=False,
            )
        )
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return panel

    def _build_ohada_table(
        self,
        title: str,
        lines: tuple[OhadaBalanceSheetLineDTO, ...],
        headers: tuple[str, ...],
        is_assets: bool,
    ) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(title, panel)
        label.setObjectName("InfoCardTitle")
        layout.addWidget(label)

        data_table, model = self._build_data_table(headers)
        v = data_table.view()
        if is_assets:
            v.setColumnWidth(0, 80)
            v.setColumnWidth(1, 300)
            v.setColumnWidth(2, 120)
            v.setColumnWidth(3, 120)
            v.setColumnWidth(4, 120)
        else:
            v.setColumnWidth(0, 80)
            v.setColumnWidth(1, 360)
            v.setColumnWidth(2, 140)

        for row_index, line in enumerate(lines):
            ref_item = self._make_item(line.reference_code or "")
            label_item = self._make_item(line.label)
            items = [ref_item, label_item]
            if is_assets:
                items.extend(
                    [
                        self._amount_item(line.gross_amount),
                        self._amount_item(line.contra_amount),
                        self._amount_item(line.net_amount),
                    ]
                )
            else:
                items.append(self._amount_item(line.net_amount))
            self._apply_ohada_row_style(items, line.row_kind_code)
            model.appendRow(items)
            v.setRowHeight(row_index, self._template_dto.row_height)

        layout.addWidget(data_table, 1)
        return panel

    def _apply_ohada_row_style(
        self,
        items: list[QStandardItem],
        row_kind_code: str,
    ) -> None:
        background_hex = self._template_dto.statement_background
        bold = False
        if row_kind_code == "section":
            background_hex = self._template_dto.section_background
            bold = True
        elif row_kind_code == "total":
            background_hex = self._template_dto.subtotal_background
            bold = True
        self._apply_item_style(items, background_hex, bold)

    def _build_ias_preview(self, report_dto: IasBalanceSheetReportDTO) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("PageCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("IAS/IFRS Balance Sheet Preview", panel)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        data_table, model = self._build_data_table(("Ref", "Line", "Amount"))
        v = data_table.view()
        v.setColumnWidth(0, 100)
        v.setColumnWidth(1, 600)
        v.setColumnWidth(2, 180)

        lines = report_dto.lines or self._fallback_ias_lines()
        for row_index, line in enumerate(lines):
            ref_item = self._make_item("" if line.row_kind_code == "section" else line.code)
            label_item = self._make_item(f"{'    ' * line.indent_level}{line.label}")
            amount_item = self._amount_item(line.amount)
            self._apply_ias_row_style([ref_item, label_item, amount_item], line.row_kind_code, line.is_formula)
            model.appendRow([ref_item, label_item, amount_item])
            v.setRowHeight(row_index, self._template_dto.row_height)

        layout.addWidget(data_table, 1)
        return panel

    def _apply_ias_row_style(
        self,
        items: list[QStandardItem],
        row_kind_code: str,
        is_formula: bool,
    ) -> None:
        background_hex = self._template_dto.statement_background
        bold = False
        if row_kind_code == "section":
            background_hex = self._template_dto.section_background
            bold = True
        elif row_kind_code == "group" or is_formula:
            background_hex = self._template_dto.subtotal_background
            bold = True
        self._apply_item_style(items, background_hex, bold)

    def _build_fallback_preview(self) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("PageCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Template Layout Preview", panel)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        note = QLabel(
            "No live balance-sheet rows are loaded yet, so this preview uses a small styled sample layout.",
            panel,
        )
        note.setObjectName("PageSummary")
        note.setWordWrap(True)
        layout.addWidget(note)

        data_table, model = self._build_data_table(("Ref", "Line", "Amount"))
        v = data_table.view()
        sample_rows = self._fallback_ias_lines()
        v.setColumnWidth(0, 100)
        v.setColumnWidth(1, 600)
        v.setColumnWidth(2, 180)
        for row_index, line in enumerate(sample_rows):
            ref_item = self._make_item("" if line.row_kind_code == "section" else line.code)
            label_item = self._make_item(f"{'    ' * line.indent_level}{line.label}")
            amount_item = self._amount_item(line.amount)
            self._apply_ias_row_style([ref_item, label_item, amount_item], line.row_kind_code, line.is_formula)
            model.appendRow([ref_item, label_item, amount_item])
            v.setRowHeight(row_index, self._template_dto.row_height)
        layout.addWidget(data_table, 1)
        return panel

    def _build_data_table(self, headers: tuple[str, ...]) -> tuple[DataTable, QStandardItemModel]:
        model = QStandardItemModel(0, len(headers), self)
        model.setHorizontalHeaderLabels(list(headers))
        table = DataTable(
            columns=tuple(DataTableColumn(key=f"col{i}", title=h) for i, h in enumerate(headers)),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=self,
        )
        table.set_model(model)
        v = table.view()
        v.verticalHeader().setVisible(False)
        v.verticalHeader().setDefaultSectionSize(28)
        v.setWordWrap(False)
        v.setShowGrid(False)
        v.setAlternatingRowColors(False)
        v.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        v.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        v.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        v.setStyleSheet(f"background: {self._template_dto.statement_background};")
        return table, model

    def _apply_item_style(
        self,
        items: list[QStandardItem],
        background_hex: str,
        bold: bool,
    ) -> None:
        background = QColor(background_hex)
        for index, item in enumerate(items):
            item.setBackground(background)
            font = item.font()
            font.setBold(bold)
            if index >= 2:
                font.setPointSize(self._template_dto.amount_font_size)
            else:
                font.setPointSize(self._template_dto.label_font_size)
            item.setFont(font)

    def _amount_item(self, amount: Decimal | None) -> QStandardItem:
        item = self._make_item("" if amount is None else self._fmt(amount))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    @staticmethod
    def _fmt(amount: Decimal | None) -> str:
        value = amount or _ZERO
        if value == _ZERO:
            return "0.00"
        return f"{value:,.2f}"

    @staticmethod
    def _fallback_ohada_asset_lines() -> tuple[OhadaBalanceSheetLineDTO, ...]:
        return (
            OhadaBalanceSheetLineDTO(
                code="AE",
                reference_code="AE",
                label="Research and development expenses",
                side_code="assets",
                section_code="fixed_assets",
                section_title="Fixed Assets",
                row_kind_code="line",
                display_order=10,
                gross_amount=Decimal("1,250.00".replace(",", "")),
                contra_amount=Decimal("220.00"),
                net_amount=Decimal("1030.00"),
                can_drilldown=False,
            ),
            OhadaBalanceSheetLineDTO(
                code="AZ",
                reference_code="AZ",
                label="TOTAL FIXED ASSETS (I)",
                side_code="assets",
                section_code="fixed_assets",
                section_title="Fixed Assets",
                row_kind_code="total",
                display_order=20,
                gross_amount=Decimal("1,250.00".replace(",", "")),
                contra_amount=Decimal("220.00"),
                net_amount=Decimal("1030.00"),
                can_drilldown=False,
            ),
        )

    @staticmethod
    def _fallback_ohada_liability_lines() -> tuple[OhadaBalanceSheetLineDTO, ...]:
        return (
            OhadaBalanceSheetLineDTO(
                code="CA",
                reference_code="CA",
                label="SHAREHOLDERS EQUITY AND ASSIMILATED SOURCES",
                side_code="liabilities",
                section_code="equity",
                section_title="Equity",
                row_kind_code="section",
                display_order=10,
                gross_amount=None,
                contra_amount=None,
                net_amount=None,
                can_drilldown=False,
            ),
            OhadaBalanceSheetLineDTO(
                code="CP",
                reference_code="CP",
                label="TOTAL SHAREHOLDERS EQUITY AND ASSIMILATED SOURCES (I)",
                side_code="liabilities",
                section_code="equity",
                section_title="Equity",
                row_kind_code="total",
                display_order=20,
                gross_amount=None,
                contra_amount=None,
                net_amount=Decimal("1030.00"),
                can_drilldown=False,
            ),
        )

    @staticmethod
    def _fallback_ias_lines() -> tuple[IasBalanceSheetLineDTO, ...]:
        return (
            IasBalanceSheetLineDTO(
                code="ASSETS",
                label="ASSETS",
                row_kind_code="section",
                parent_code=None,
                display_order=10,
                indent_level=0,
                amount=None,
                can_drilldown=False,
                is_formula=False,
                is_classification_target=False,
            ),
            IasBalanceSheetLineDTO(
                code="NON_CURRENT_ASSETS",
                label="Non-current assets",
                row_kind_code="group",
                parent_code="ASSETS",
                display_order=20,
                indent_level=0,
                amount=Decimal("1800.00"),
                can_drilldown=False,
                is_formula=False,
                is_classification_target=False,
            ),
            IasBalanceSheetLineDTO(
                code="TOTAL_ASSETS",
                label="TOTAL ASSETS",
                row_kind_code="formula",
                parent_code=None,
                display_order=30,
                indent_level=0,
                amount=Decimal("1800.00"),
                can_drilldown=False,
                is_formula=True,
                is_classification_target=False,
            ),
        )

    @classmethod
    def show_preview(
        cls,
        template_dto: BalanceSheetTemplateDTO,
        report_dto: OhadaBalanceSheetReportDTO | IasBalanceSheetReportDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        dialog = cls(template_dto, report_dto, parent)
        dialog.exec()
