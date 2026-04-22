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
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.ohada_income_statement_dto import (
    OhadaIncomeStatementLineDTO,
    OhadaIncomeStatementReportDTO,
)
from seeker_accounting.modules.reporting.dto.ohada_income_statement_template_dto import (
    OhadaIncomeStatementTemplateDTO,
)
from seeker_accounting.modules.reporting.dto.print_preview_dto import (
    PrintPreviewMetaDTO,
    PrintPreviewRowDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)
from seeker_accounting.modules.reporting.ui.dialogs.ohada_income_statement_line_detail_dialog import (
    OhadaIncomeStatementLineDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.ohada_income_statement_template_preview_dialog import (
    OhadaIncomeStatementTemplatePreviewDialog,
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
from seeker_accounting.shared.ui.help_button import install_help_button
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_ZERO = Decimal("0.00")


class OhadaIncomeStatementWindow(QFrame):
    """Focused child window for the locked OHADA income statement."""

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
        self._report_service = service_registry.ohada_income_statement_service
        self._template_service = service_registry.ohada_income_statement_template_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )

        resolved_company_id = company_id or self._active_company_context.company_id
        self._current_filter = ReportingFilterDTO(
            company_id=resolved_company_id,
            date_from=initial_filter.date_from if initial_filter else None,
            date_to=initial_filter.date_to if initial_filter else None,
            posted_only=True if initial_filter is None else initial_filter.posted_only,
        )
        self._current_report: OhadaIncomeStatementReportDTO | None = None
        self._current_template = self._template_service.get_template(None)

        self.setObjectName("OhadaIncomeStatementWindow")
        self.setWindowTitle("OHADA Income Statement")
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
        install_help_button(self, "dialog.ohada_income_statement", dialog=True)

    def _build_context_strip(self) -> QWidget:
        strip = ReportingContextStrip(self._context_service, self._service_registry, self)
        layout = strip.layout()

        today = datetime.date.today()
        first = today.replace(day=1)

        # Insert before the trailing stretch so dates sit next to BASIS
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

    def _build_filter_bar(self) -> QWidget:
        self._filter_bar = ReportingFilterBar(self)
        self._filter_bar.refresh_requested.connect(self._on_refresh_requested)
        self._filter_bar.print_preview_requested.connect(self._on_print_preview_requested)
        self._filter_bar.template_preview_requested.connect(self._on_template_preview_requested)
        self._filter_bar.export_requested.connect(self._on_export_requested)
        self._filter_bar.show_export_button()

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

        # Hide date widgets now in context strip (original indices shift by 4)
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
        layout.setSpacing(12)
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
            ("XA", "Commercial Margin"),
            ("XE", "Operating Result"),
            ("XG", "Ordinary Activities"),
            ("XH", "Off Ordinary Activities"),
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
                message="Select an active company before opening the OHADA income statement.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No OHADA Coverage",
                message=(
                    "The company chart does not currently expose the locked OHADA prefixes required "
                    "for this statement."
                ),
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Posted Activity",
                message="No posted OHADA activity was found for the selected reporting period.",
                parent=self,
            )
        )
        return self._stack

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 0, 20, 20)
        layout.setSpacing(0)

        self._table = QTableWidget(panel)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Ref", "Line", "Signed Amount"])
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_table_double_clicked)
        self._table.setColumnWidth(0, 90)
        self._table.setColumnWidth(1, 620)
        self._table.setColumnWidth(2, 180)
        layout.addWidget(self._table)
        return panel

    def _load_templates(self) -> None:
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        for template in self._template_service.list_templates():
            self._template_combo.addItem(template.template_title, template.template_code)
        self._template_combo.blockSignals(False)
        self._select_template(self._current_template.template_code)

    def _select_template(self, template_code: str) -> None:
        for index in range(self._template_combo.count()):
            if self._template_combo.itemData(index) == template_code:
                self._template_combo.setCurrentIndex(index)
                break

    def _sync_filter_context(self) -> None:
        company_name = self._active_company_context.company_name or ""
        self._filter_bar.set_company_context(self._current_filter.company_id, company_name)
        self._filter_bar.set_filter(self._current_filter)
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
            self._warning_band.hide()
            self._review_unclassified_btn.setEnabled(False)
            self._stack.setCurrentIndex(1)
            return

        try:
            report = self._report_service.get_statement(self._current_filter)
        except ValidationError as exc:
            show_error(self, "OHADA Income Statement", str(exc))
            self._stack.setCurrentIndex(1)
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "OHADA Income Statement", str(exc))
            self._stack.setCurrentIndex(1)
            return

        self._current_report = report
        self._update_warning_band(report)
        self._update_summary_strip(report)
        self._review_unclassified_btn.setEnabled(bool(report.unclassified_accounts))

        if not report.has_chart_coverage:
            self._stack.setCurrentIndex(2)
            return
        if not report.has_posted_activity and not report.unclassified_accounts:
            self._stack.setCurrentIndex(3)
            return

        self._bind_report(report)
        self._stack.setCurrentIndex(0)

    def _update_warning_band(self, report: OhadaIncomeStatementReportDTO) -> None:
        if not report.warnings:
            self._warning_band.hide()
            return
        self._warning_label.setText(" | ".join(warning.message for warning in report.warnings))
        self._warning_band.show()

    def _update_summary_strip(self, report: OhadaIncomeStatementReportDTO) -> None:
        line_lookup = {line.code: line for line in report.lines}
        for code, label in self._summary_values.items():
            line = line_lookup.get(code)
            label.setText(self._fmt(line.signed_amount if line else _ZERO))

    def _bind_report(self, report: OhadaIncomeStatementReportDTO) -> None:
        template = self._current_template
        rows: list[tuple[str, str | None, str, Decimal | None, OhadaIncomeStatementLineDTO | None]] = []
        current_section = None
        for line in report.lines:
            if line.section_title != current_section:
                current_section = line.section_title
                rows.append(("section", None, current_section, None, None))
            row_type = "subtotal" if line.is_formula else "line"
            rows.append((row_type, line.code, line.label, line.signed_amount, line))

        self._table.setRowCount(len(rows))
        for row_index, row_data in enumerate(rows):
            row_type, ref, label, amount, line = row_data
            ref_item = QTableWidgetItem(ref or "")
            label_item = QTableWidgetItem(label)
            amount_item = QTableWidgetItem("" if amount is None else self._fmt(amount))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if line is not None:
                ref_item.setData(Qt.ItemDataRole.UserRole, line.code)
                ref_item.setData(Qt.ItemDataRole.UserRole + 1, line.can_drilldown)

            if row_type == "section":
                self._apply_row_style(
                    ref_item,
                    label_item,
                    amount_item,
                    background_hex=template.section_background,
                    bold=True,
                )
                self._table.setRowHeight(row_index, template.row_height + 2)
            elif row_type == "subtotal":
                self._apply_row_style(
                    ref_item,
                    label_item,
                    amount_item,
                    background_hex=template.subtotal_background,
                    bold=True,
                )
                self._table.setRowHeight(row_index, template.row_height)
            else:
                self._apply_row_style(
                    ref_item,
                    label_item,
                    amount_item,
                    background_hex=template.statement_background,
                    bold=False,
                )
                self._table.setRowHeight(row_index, template.row_height)

            self._table.setItem(row_index, 0, ref_item)
            self._table.setItem(row_index, 1, label_item)
            self._table.setItem(row_index, 2, amount_item)

    def _apply_row_style(
        self,
        ref_item: QTableWidgetItem,
        label_item: QTableWidgetItem,
        amount_item: QTableWidgetItem,
        *,
        background_hex: str,
        bold: bool,
    ) -> None:
        background = QColor(background_hex)
        for item in (ref_item, label_item):
            item.setBackground(background)
            font = item.font()
            font.setBold(bold)
            font.setPointSize(self._current_template.label_font_size)
            item.setFont(font)
        amount_item.setBackground(background)
        amount_font = amount_item.font()
        amount_font.setBold(bold)
        amount_font.setPointSize(self._current_template.amount_font_size)
        amount_item.setFont(amount_font)

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
            posted_only=filter_dto.posted_only,
        )
        self._sync_filter_context()
        self._load_report()

    def _on_template_changed(self, index: int) -> None:  # noqa: ARG002
        template_code = self._template_combo.currentData()
        self._current_template = self._template_service.get_template(
            template_code if isinstance(template_code, str) else None
        )
        if self._current_report is not None:
            self._bind_report(self._current_report)

    def _on_template_preview_requested(self, meta: object) -> None:  # noqa: ARG002
        OhadaIncomeStatementTemplatePreviewDialog.show_preview(
            template_dto=self._current_template,
            report_dto=self._current_report,
            parent=self,
        )

    def _on_print_preview_requested(self, meta: object) -> None:  # noqa: ARG002
        if self._current_report is None:
            return
        period_label = "-"
        if self._current_filter.date_from and self._current_filter.date_to:
            period_label = (
                f"{self._current_filter.date_from.strftime('%d %b %Y')} - "
                f"{self._current_filter.date_to.strftime('%d %b %Y')}"
            )
        company_name = self._active_company_context.company_name or "Unknown Company"
        preview_meta = PrintPreviewMetaDTO(
            report_title="OHADA Income Statement",
            company_name=company_name,
            period_label=period_label,
            generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=f"Posted Only: {self._current_filter.posted_only}",
            template_title=self._current_template.template_title,
            rows=tuple(self._build_preview_rows(self._current_report)),
        )
        ReportPrintPreviewDialog.show_preview(preview_meta, parent=self)

    def _on_export_requested(self) -> None:
        if self._current_report is None:
            return
        result = FinancialStatementExportDialog.show_dialog(
            self, "OHADA Income Statement - Compte de Résultat",
        )
        if result is None:
            return
        try:
            export_service = self._service_registry.income_statement_export_service
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
            detail = self._report_service.list_unclassified_accounts(self._current_filter)
        except ValidationError as exc:
            show_error(self, "OHADA Income Statement", str(exc))
            return
        OhadaIncomeStatementLineDetailDialog.open(
            service_registry=self._service_registry,
            detail_dto=detail,
            filter_dto=self._current_filter,
            parent=self,
        )

    def _on_table_double_clicked(self, row: int, column: int) -> None:  # noqa: ARG002
        ref_item = self._table.item(row, 0)
        if ref_item is None:
            return
        line_code = ref_item.data(Qt.ItemDataRole.UserRole)
        can_drilldown = ref_item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(line_code, str) or not can_drilldown:
            return
        try:
            detail = self._report_service.get_line_detail(self._current_filter, line_code)
        except (ValidationError, NotFoundError) as exc:
            show_error(self, "OHADA Income Statement", str(exc))
            return
        OhadaIncomeStatementLineDetailDialog.open(
            service_registry=self._service_registry,
            detail_dto=detail,
            filter_dto=self._current_filter,
            parent=self,
        )

    def _build_preview_rows(self, report: OhadaIncomeStatementReportDTO) -> list[PrintPreviewRowDTO]:
        rows: list[PrintPreviewRowDTO] = []
        current_section = None
        for line in report.lines:
            if line.section_title != current_section:
                current_section = line.section_title
                rows.append(
                    PrintPreviewRowDTO(
                        row_type="section",
                        reference_code=None,
                        label=current_section,
                    )
                )
            rows.append(
                PrintPreviewRowDTO(
                    row_type="subtotal" if line.is_formula else "line",
                    reference_code=line.code,
                    label=line.label,
                    amount_text=self._fmt(line.signed_amount),
                )
            )
        return rows

    @staticmethod
    def _fmt(amount: Decimal) -> str:
        if amount == _ZERO:
            return "0.00"
        return f"{amount:,.2f}"

    @classmethod
    def open(
        cls,
        service_registry: ServiceRegistry,
        company_id: int | None,
        initial_filter: ReportingFilterDTO | None = None,
        parent: QWidget | None = None,
    ) -> "OhadaIncomeStatementWindow":
        window = cls(service_registry, company_id, initial_filter=initial_filter, parent=parent)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        if parent is not None:
            child_windows = getattr(parent, "_report_child_windows", None)
            if child_windows is None:
                child_windows = []
                setattr(parent, "_report_child_windows", child_windows)
            child_windows.append(window)

            def _cleanup() -> None:
                if window in child_windows:
                    child_windows.remove(window)

            window.destroyed.connect(_cleanup)

        window.show()
        window.raise_()
        window.activateWindow()
        return window
