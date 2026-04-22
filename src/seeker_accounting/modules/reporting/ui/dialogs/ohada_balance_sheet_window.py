from __future__ import annotations

import datetime
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.ohada_balance_sheet_dto import (
    OhadaBalanceSheetLineDTO,
    OhadaBalanceSheetReportDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)
from seeker_accounting.modules.reporting.ui.dialogs.balance_sheet_line_detail_dialog import (
    OhadaBalanceSheetLineDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.balance_sheet_template_preview_dialog import (
    BalanceSheetTemplatePreviewDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.report_print_preview_dialog import (
    ReportPrintPreviewDialog,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_context_strip import (
    ReportingContextStrip,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_empty_state import (
    ReportingEmptyState,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_filter_bar import (
    ReportingFilterBar,
)
from seeker_accounting.modules.reporting.ui.dialogs.financial_statement_export_dialog import (
    FinancialStatementExportDialog,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_ZERO = Decimal("0.00")


class OhadaBalanceSheetWindow(QFrame):
    """Focused child window for the OHADA balance sheet."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._active_company_context = service_registry.active_company_context
        self._report_service = service_registry.ohada_balance_sheet_service
        self._template_service = service_registry.balance_sheet_template_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )

        resolved_company_id = company_id or self._active_company_context.company_id
        self._current_filter = ReportingFilterDTO(
            company_id=resolved_company_id,
            date_from=initial_filter.date_from if initial_filter else None,
            date_to=initial_filter.date_to if initial_filter else None,
            posted_only=True,
        )
        self._current_report: OhadaBalanceSheetReportDTO | None = None
        self._current_template = self._template_service.get_template(None)

        self.setObjectName("OhadaBalanceSheetWindow")
        self.setWindowTitle("OHADA Balance Sheet")
        self.setMinimumSize(960, 620)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_context_strip())
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_warning_band())
        root.addWidget(self._build_summary_strip())
        root.addWidget(self._build_content_stack(), 1)

        self._ctx_date_from.dateChanged.connect(self._filter_bar._date_from.setDate)
        self._ctx_date_to.dateChanged.connect(self._filter_bar._date_to.setDate)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._load_templates()
        if initial_filter is not None:
            self._filter_bar.set_filter(initial_filter)
        self._sync_filter_context()
        self._current_filter = self._filter_bar.get_filter()
        self._load_report()

    def _build_context_strip(self) -> QWidget:
        strip = ReportingContextStrip(self._context_service, self._service_registry, self)
        layout = strip.layout()

        today = datetime.date.today()
        first = today.replace(day=1)

        # Insert before the trailing stretch so dates sit inline in the context bar
        pos = layout.count() - 1

        sep = QFrame(strip)
        sep.setFixedWidth(1)
        sep.setFixedHeight(16)
        sep.setStyleSheet("background: palette(mid);")
        layout.insertWidget(pos, sep, 0, Qt.AlignmentFlag.AlignVCenter)
        pos += 1

        from_lbl = QLabel("FROM", strip)
        from_lbl.setProperty("role", "caption")
        layout.insertWidget(pos, from_lbl)
        pos += 1

        self._ctx_date_from = QDateEdit(strip)
        self._ctx_date_from.setDate(QDate(first.year, first.month, first.day))
        self._ctx_date_from.setCalendarPopup(True)
        self._ctx_date_from.setFixedWidth(108)
        layout.insertWidget(pos, self._ctx_date_from)
        pos += 1

        to_lbl = QLabel("TO", strip)
        to_lbl.setProperty("role", "caption")
        layout.insertWidget(pos, to_lbl)
        pos += 1

        self._ctx_date_to = QDateEdit(strip)
        self._ctx_date_to.setDate(QDate(today.year, today.month, today.day))
        self._ctx_date_to.setCalendarPopup(True)
        self._ctx_date_to.setFixedWidth(108)
        layout.insertWidget(pos, self._ctx_date_to)

        return strip

    def _build_header(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(18)

        title_block = QWidget(card)
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(4)

        eyebrow = QLabel("Balance Sheet | OHADA", title_block)
        eyebrow.setProperty("role", "caption")
        title_layout.addWidget(eyebrow)

        title = QLabel("OHADA Balance Sheet", title_block)
        title.setObjectName("PageTitle")
        title_layout.addWidget(title)

        summary = QLabel(
            "Locked OHADA balance sheet using the authoritative OHADA asset and liability structure with drilldown and print preview.",
            title_block,
        )
        summary.setObjectName("PageSummary")
        summary.setWordWrap(True)
        title_layout.addWidget(summary)
        layout.addWidget(title_block, 1)

        controls = QWidget(card)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        template_caption = QLabel("Presentation Template", controls)
        template_caption.setProperty("role", "caption")
        controls_layout.addWidget(template_caption)

        self._template_combo = QComboBox(controls)
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        controls_layout.addWidget(self._template_combo)

        self._review_unclassified_btn = QPushButton("Review Unclassified", controls)
        self._review_unclassified_btn.setProperty("variant", "secondary")
        self._review_unclassified_btn.clicked.connect(self._on_review_unclassified)
        self._review_unclassified_btn.setEnabled(False)
        controls_layout.addWidget(self._review_unclassified_btn)
        layout.addWidget(controls)
        return card

    def _build_filter_bar(self) -> QWidget:
        self._filter_bar = ReportingFilterBar(self)
        self._filter_bar.refresh_requested.connect(self._on_refresh_requested)
        self._filter_bar.print_preview_requested.connect(self._on_print_preview_requested)
        self._filter_bar.template_preview_requested.connect(self._on_template_preview_requested)
        self._filter_bar.export_requested.connect(self._on_export_requested)
        self._filter_bar.show_export_button()
        self._filter_bar._posted_only.setChecked(True)
        self._filter_bar._posted_only.setEnabled(False)

        fl = self._filter_bar.layout()

        self._review_unclassified_btn = QPushButton("Review Unclassified", self._filter_bar)
        self._review_unclassified_btn.setProperty("variant", "secondary")
        self._review_unclassified_btn.clicked.connect(self._on_review_unclassified)
        self._review_unclassified_btn.setEnabled(False)
        fl.insertWidget(0, self._review_unclassified_btn)

        sep = QFrame(self._filter_bar)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        fl.insertWidget(0, sep)

        self._template_combo = QComboBox(self._filter_bar)
        self._template_combo.setFixedWidth(172)
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        fl.insertWidget(0, self._template_combo)

        template_lbl = QLabel("Template:", self._filter_bar)
        template_lbl.setProperty("role", "caption")
        fl.insertWidget(0, template_lbl)

        # Hide date widgets now embedded in context strip (original indices shift by 4)
        for idx in (7, 6, 5, 4):
            item = fl.itemAt(idx)
            if item and item.widget():
                item.widget().hide()

        return self._filter_bar

    def _build_warning_band(self) -> QWidget:
        self._warning_band = QFrame(self)
        self._warning_band.setObjectName("PageCard")
        layout = QHBoxLayout(self._warning_band)
        layout.setContentsMargins(16, 10, 16, 10)
        self._warning_label = QLabel(self._warning_band)
        self._warning_label.setObjectName("PageSummary")
        self._warning_label.setWordWrap(True)
        layout.addWidget(self._warning_label, 1)
        self._warning_band.hide()
        return self._warning_band

    def _build_summary_strip(self) -> QWidget:
        strip = QWidget(self)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(8)
        self._summary_values: dict[str, QLabel] = {}

        for code, title in (
            ("assets", "Total Assets"),
            ("liabilities", "Total Liab. + Equity"),
            ("difference", "Difference"),
        ):
            card = QFrame(strip)
            card.setObjectName("InfoCard")
            card.setProperty("card", True)
            card.setFixedHeight(34)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(10, 0, 10, 0)
            card_layout.setSpacing(8)

            caption = QLabel(title, card)
            caption.setProperty("role", "caption")
            card_layout.addWidget(caption)

            card_layout.addStretch(1)

            value = QLabel("0.00", card)
            value.setObjectName("InfoCardTitle")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            card_layout.addWidget(value)

            layout.addWidget(card, 1)
            self._summary_values[code] = value
        return strip

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_table_panel())
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Active Company",
                message="Select an active company before opening the OHADA balance sheet.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Posted Balances",
                message="No posted balance sheet activity was found up to the selected statement date.",
                parent=self,
            )
        )
        return self._stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 0, 20, 20)

        splitter = QSplitter(Qt.Orientation.Horizontal, panel)
        splitter.addWidget(self._build_assets_panel(splitter))
        splitter.addWidget(self._build_liabilities_panel(splitter))
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        return panel

    def _build_assets_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("Assets", panel)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        self._assets_table = QTableWidget(panel)
        self._assets_table.setColumnCount(5)
        self._assets_table.setHorizontalHeaderLabels(["Ref", "Line", "Gross", "Deprec./Prov.", "Net"])
        configure_compact_table(self._assets_table)
        self._assets_table.setSortingEnabled(False)
        self._assets_table.cellDoubleClicked.connect(self._on_assets_double_clicked)
        layout.addWidget(self._assets_table, 1)
        return panel

    def _build_liabilities_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("Liabilities and Equity", panel)
        title.setObjectName("InfoCardTitle")
        layout.addWidget(title)

        self._liabilities_table = QTableWidget(panel)
        self._liabilities_table.setColumnCount(3)
        self._liabilities_table.setHorizontalHeaderLabels(["Ref", "Line", "Amount"])
        configure_compact_table(self._liabilities_table)
        self._liabilities_table.setSortingEnabled(False)
        self._liabilities_table.cellDoubleClicked.connect(self._on_liabilities_double_clicked)
        layout.addWidget(self._liabilities_table, 1)
        return panel

    def _load_templates(self) -> None:
        self._template_combo.blockSignals(True)
        try:
            self._template_combo.clear()
            for template in self._template_service.list_templates():
                self._template_combo.addItem(template.template_title, template.template_code)
            self._template_combo.setCurrentIndex(0)
            self._current_template = self._template_service.get_template(self._template_combo.currentData())
        finally:
            self._template_combo.blockSignals(False)

    def _sync_filter_context(self) -> None:
        company_name = self._active_company_context.company_name or ""
        self._current_filter.posted_only = True
        self._filter_bar.set_company_context(self._current_filter.company_id, company_name)
        self._filter_bar.set_filter(self._current_filter)
        self._filter_bar._posted_only.setChecked(True)
        if self._current_filter.date_from:
            d = self._current_filter.date_from
            self._ctx_date_from.setDate(QDate(d.year, d.month, d.day))
        if self._current_filter.date_to:
            d = self._current_filter.date_to
            self._ctx_date_to.setDate(QDate(d.year, d.month, d.day))

    def _load_report(self) -> None:
        company_id = self._current_filter.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            self._current_report = None
            self._review_unclassified_btn.setEnabled(False)
            self._stack.setCurrentIndex(1)
            return

        try:
            report = self._report_service.get_statement(
                self._current_filter,
                self._current_template.template_code,
            )
        except ValidationError as exc:
            show_error(self, "OHADA Balance Sheet", str(exc))
            self._stack.setCurrentIndex(1)
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "OHADA Balance Sheet", str(exc))
            self._stack.setCurrentIndex(1)
            return

        self._current_report = report
        self._review_unclassified_btn.setEnabled(bool(report.unclassified_accounts))
        self._update_warning_band(report)
        self._update_summary_strip(report)

        if not report.has_posted_activity:
            self._stack.setCurrentIndex(2)
            return

        self._bind_assets(report.asset_lines)
        self._bind_liabilities(report.liability_lines)
        self._stack.setCurrentIndex(0)

    def _update_warning_band(self, report: OhadaBalanceSheetReportDTO) -> None:
        if not report.warnings:
            self._warning_band.hide()
            return
        self._warning_label.setText(" | ".join(warning.message for warning in report.warnings))
        self._warning_band.show()

    def _update_summary_strip(self, report: OhadaBalanceSheetReportDTO) -> None:
        self._summary_values["assets"].setText(self._fmt(report.total_assets))
        self._summary_values["liabilities"].setText(self._fmt(report.total_liabilities_and_equity))
        self._summary_values["difference"].setText(self._fmt(report.balance_difference))

    def _bind_assets(self, lines: tuple[OhadaBalanceSheetLineDTO, ...]) -> None:
        template = self._current_template
        self._assets_table.setRowCount(len(lines))
        for row_index, line in enumerate(lines):
            ref_item = QTableWidgetItem(line.reference_code or "")
            ref_item.setData(Qt.ItemDataRole.UserRole, line.code)
            ref_item.setData(Qt.ItemDataRole.UserRole + 1, line.can_drilldown)
            label_item = QTableWidgetItem(line.label)
            gross_item = self._amount_item(line.gross_amount)
            contra_item = self._amount_item(line.contra_amount)
            net_item = self._amount_item(line.net_amount)
            self._apply_row_style(ref_item, label_item, gross_item, contra_item, net_item, line.row_kind_code, template)
            self._assets_table.setRowHeight(row_index, template.row_height)
            self._assets_table.setItem(row_index, 0, ref_item)
            self._assets_table.setItem(row_index, 1, label_item)
            self._assets_table.setItem(row_index, 2, gross_item)
            self._assets_table.setItem(row_index, 3, contra_item)
            self._assets_table.setItem(row_index, 4, net_item)

    def _bind_liabilities(self, lines: tuple[OhadaBalanceSheetLineDTO, ...]) -> None:
        template = self._current_template
        self._liabilities_table.setRowCount(len(lines))
        for row_index, line in enumerate(lines):
            ref_item = QTableWidgetItem(line.reference_code or "")
            ref_item.setData(Qt.ItemDataRole.UserRole, line.code)
            ref_item.setData(Qt.ItemDataRole.UserRole + 1, line.can_drilldown)
            label_item = QTableWidgetItem(line.label)
            amount_item = self._amount_item(line.net_amount)
            self._apply_row_style(ref_item, label_item, amount_item, None, None, line.row_kind_code, template)
            self._liabilities_table.setRowHeight(row_index, template.row_height)
            self._liabilities_table.setItem(row_index, 0, ref_item)
            self._liabilities_table.setItem(row_index, 1, label_item)
            self._liabilities_table.setItem(row_index, 2, amount_item)

    def _apply_row_style(
        self,
        ref_item: QTableWidgetItem,
        label_item: QTableWidgetItem,
        amount_a: QTableWidgetItem | None,
        amount_b: QTableWidgetItem | None,
        amount_c: QTableWidgetItem | None,
        row_kind_code: str,
        template,
    ) -> None:
        background_hex = template.statement_background
        bold = False
        if row_kind_code == "section":
            background_hex = template.section_background
            bold = True
        elif row_kind_code == "total":
            background_hex = template.subtotal_background
            bold = True

        background = QColor(background_hex)
        for item in (ref_item, label_item, amount_a, amount_b, amount_c):
            if item is None:
                continue
            item.setBackground(background)
            font = item.font()
            font.setBold(bold)
            font.setPointSize(template.label_font_size)
            item.setFont(font)
        for item in (amount_a, amount_b, amount_c):
            if item is None:
                continue
            font = item.font()
            font.setBold(bold)
            font.setPointSize(template.amount_font_size)
            item.setFont(font)

    def _amount_item(self, amount: Decimal | None) -> QTableWidgetItem:
        item = QTableWidgetItem("" if amount is None else self._fmt(amount))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if isinstance(company_id, int):
            self._current_filter.company_id = company_id
            self._sync_filter_context()
            self._load_report()

    def _on_refresh_requested(self, filter_dto: object) -> None:
        if not isinstance(filter_dto, ReportingFilterDTO):
            return
        self._current_filter = ReportingFilterDTO(
            company_id=filter_dto.company_id or self._active_company_context.company_id,
            date_from=filter_dto.date_from,
            date_to=filter_dto.date_to,
            posted_only=True,
        )
        self._sync_filter_context()
        self._load_report()

    def _on_template_changed(self, index: int) -> None:  # noqa: ARG002
        self._current_template = self._template_service.get_template(self._template_combo.currentData())
        if self._current_report is not None:
            self._bind_assets(self._current_report.asset_lines)
            self._bind_liabilities(self._current_report.liability_lines)

    def _on_template_preview_requested(self, meta: object) -> None:  # noqa: ARG002
        BalanceSheetTemplatePreviewDialog.show_preview(
            self._current_template,
            self._current_report,
            parent=self,
        )

    def _on_print_preview_requested(self, meta: object) -> None:  # noqa: ARG002
        if self._current_report is None:
            return
        company_name = self._active_company_context.company_name or "Unknown Company"
        preview_meta = self._report_service.build_print_preview_meta(self._current_report, company_name)
        ReportPrintPreviewDialog.show_preview(preview_meta, parent=self)

    def _on_export_requested(self) -> None:
        if self._current_report is None:
            return
        result = FinancialStatementExportDialog.show_dialog(
            self, "OHADA Balance Sheet - Bilan",
        )
        if result is None:
            return
        try:
            export_service = self._service_registry.balance_sheet_export_service
            export_service.export_ohada(
                self._current_report,
                self._current_filter.company_id,
                result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Export Failed", str(exc))

    def _on_review_unclassified(self) -> None:
        try:
            detail = self._report_service.list_unclassified_accounts(
                self._current_filter,
                self._current_template.template_code,
            )
        except ValidationError as exc:
            show_error(self, "OHADA Balance Sheet", str(exc))
            return
        OhadaBalanceSheetLineDetailDialog.open(self._service_registry, detail, parent=self)

    def _open_line_detail(self, line_code: str) -> None:
        try:
            detail = self._report_service.get_line_detail(
                self._current_filter,
                line_code,
                self._current_template.template_code,
            )
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "OHADA Balance Sheet", str(exc))
            return
        OhadaBalanceSheetLineDetailDialog.open(self._service_registry, detail, parent=self)

    def _on_assets_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        ref_item = self._assets_table.item(row, 0)
        if ref_item is None or not ref_item.data(Qt.ItemDataRole.UserRole + 1):
            return
        line_code = ref_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(line_code, str):
            self._open_line_detail(line_code)

    def _on_liabilities_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        ref_item = self._liabilities_table.item(row, 0)
        if ref_item is None or not ref_item.data(Qt.ItemDataRole.UserRole + 1):
            return
        line_code = ref_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(line_code, str):
            self._open_line_detail(line_code)

    @staticmethod
    def _fmt(amount: Decimal | None) -> str:
        value = amount or _ZERO
        if value == _ZERO:
            return "0.00"
        return f"{value:,.2f}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> None:
        window = cls(service_registry, company_id, initial_filter=initial_filter, parent=parent)
        window.show()
