from __future__ import annotations

from decimal import Decimal

import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.ias_income_statement_dto import (
    IasIncomeStatementLineDTO,
    IasIncomeStatementReportDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)
from seeker_accounting.modules.reporting.ui.dialogs.ias_income_statement_line_detail_dialog import (
    IasIncomeStatementLineDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.ias_income_statement_mapping_dialog import (
    IasIncomeStatementMappingDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.ias_income_statement_template_preview_dialog import (
    IasIncomeStatementTemplatePreviewDialog,
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


class IasIncomeStatementWindow(QDialog):
    """Focused child window for the IAS/IFRS income statement builder."""

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
        self._report_service = service_registry.ias_income_statement_service
        self._mapping_service = service_registry.ias_income_statement_mapping_service
        self._template_service = service_registry.ias_income_statement_template_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )
        _perm = service_registry.permission_service
        self._can_manage_mappings = _perm.has_permission("reports.ias_mappings.manage")
        self._can_view_unmapped = _perm.has_permission("reports.ias_mappings.view")

        resolved_company_id = company_id or self._active_company_context.company_id
        self._current_filter = ReportingFilterDTO(
            company_id=resolved_company_id,
            date_from=initial_filter.date_from if initial_filter else None,
            date_to=initial_filter.date_to if initial_filter else None,
            posted_only=True,
        )
        self._current_report: IasIncomeStatementReportDTO | None = None
        self._current_template = self._template_service.get_template(None)

        self.setObjectName("IasIncomeStatementWindow")
        self.setWindowTitle("IAS Income Statement Builder")
        self.setMinimumSize(960, 620)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_context_strip())
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_warning_band())
        root.addWidget(self._build_summary_strip())
        root.addWidget(self._build_content_stack(), 1)

        # keep filter bar's hidden date widgets in sync with context strip pickers
        self._ctx_date_from.dateChanged.connect(self._filter_bar._date_from.setDate)
        self._ctx_date_to.dateChanged.connect(self._filter_bar._date_to.setDate)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._load_templates()
        if initial_filter is not None:
            self._filter_bar.set_filter(initial_filter)
        self._sync_filter_context()
        self._current_filter = self._filter_bar.get_filter()
        self._load_report()
        self._manage_mappings_btn.setEnabled(self._can_manage_mappings)
        install_help_button(self, "dialog.ias_income_statement_builder", dialog=True)

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
        layout.addWidget(self._ctx_date_to)

        return strip

    def _build_filter_bar(self) -> QWidget:
        self._filter_bar = ReportingFilterBar(self)
        self._filter_bar.refresh_requested.connect(self._on_refresh_requested)
        self._filter_bar.print_preview_requested.connect(self._on_print_preview_requested)
        self._filter_bar.template_preview_requested.connect(self._on_template_preview_requested)
        self._filter_bar.export_requested.connect(self._on_export_requested)
        self._filter_bar.show_export_button()
        self._filter_bar._posted_only.setChecked(True)
        self._filter_bar._posted_only.setEnabled(False)

        # Prepend template selector + mapping buttons into the single filter row,
        # and hide the date fields (dates moved to context strip).
        fl = self._filter_bar.layout()

        self._review_unmapped_btn = QPushButton("Review Unmapped", self._filter_bar)
        self._review_unmapped_btn.setProperty("variant", "secondary")
        self._review_unmapped_btn.clicked.connect(self._on_review_unmapped)
        self._review_unmapped_btn.setEnabled(False)
        fl.insertWidget(0, self._review_unmapped_btn)

        self._manage_mappings_btn = QPushButton("Manage Mappings", self._filter_bar)
        self._manage_mappings_btn.setProperty("variant", "secondary")
        self._manage_mappings_btn.clicked.connect(self._on_manage_mappings)
        fl.insertWidget(0, self._manage_mappings_btn)

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

        # Hide date widgets from filter bar (now shown in context strip)
        # After 5 insertions above, original filter bar items shift by 5:
        # index 5=from_lbl, 6=_date_from, 7=to_lbl, 8=_date_to
        for idx in (8, 7, 6, 5):
            item = fl.itemAt(idx)
            if item and item.widget():
                item.widget().hide()

        return self._filter_bar

    def _build_warning_band(self) -> QWidget:
        self._warning_band = QFrame(self)
        self._warning_band.setObjectName("PageCard")
        layout = QHBoxLayout(self._warning_band)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(8)
        self._warning_label = QLabel(self._warning_band)
        self._warning_label.setObjectName("PageSummary")
        self._warning_label.setWordWrap(False)
        layout.addWidget(self._warning_label, 1)

        self._warning_issues_btn = QPushButton("\u26A0", self._warning_band)
        self._warning_issues_btn.setToolTip("View all validation issues")
        self._warning_issues_btn.setProperty("variant", "ghost")
        self._warning_issues_btn.setFixedSize(24, 20)
        self._warning_issues_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._warning_issues_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._warning_issues_btn.clicked.connect(self._show_warning_issues_dialog)
        layout.addWidget(self._warning_issues_btn)

        self._warning_band.hide()
        return self._warning_band

    def _build_summary_strip(self) -> QWidget:
        strip = QWidget(self)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(8)
        self._summary_values: dict[str, QLabel] = {}

        for code, title in (
            ("GROSS_PROFIT", "Gross Profit"),
            ("OPERATING_PROFIT", "Operating Profit"),
            ("PROFIT_BEFORE_TAX", "Profit Before Tax"),
            ("PROFIT_FOR_PERIOD", "Profit for the Period"),
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
                message="Select an active company before opening the IAS/IFRS income statement.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No IAS Mappings Yet",
                message=(
                    "No active IAS mappings exist for this company. Use Manage Mappings to assign "
                    "accounts to the locked IAS sections."
                ),
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Posted Activity",
                message="No posted journal activity was found for the selected reporting period.",
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
        self._table.setHorizontalHeaderLabels(["Ref", "Line", "Amount"])
        configure_compact_table(self._table)
        self._table.setSortingEnabled(False)
        self._table.cellDoubleClicked.connect(self._on_table_double_clicked)
        self._table.setColumnWidth(0, 92)
        self._table.setColumnWidth(1, 720)
        self._table.setColumnWidth(2, 180)
        layout.addWidget(self._table)
        return panel

    def _load_templates(self) -> None:
        self._template_combo.blockSignals(True)
        try:
            self._template_combo.clear()
            for template in self._template_service.list_templates():
                self._template_combo.addItem(template.template_title, template.template_code)
            try:
                preferred_code = self._template_service.get_company_template_code(self._current_filter.company_id)
            except Exception:  # pragma: no cover - defensive preference fallback
                preferred_code = None
            self._select_template(preferred_code)
        finally:
            self._template_combo.blockSignals(False)

    def _select_template(self, template_code: str | None) -> None:
        if self._template_combo.count() == 0:
            return
        selected_index = -1
        for index in range(self._template_combo.count()):
            if self._template_combo.itemData(index) == template_code:
                selected_index = index
                break
        if selected_index < 0:
            selected_index = 0
        self._template_combo.setCurrentIndex(selected_index)
        selected_code = self._template_combo.itemData(selected_index)
        self._current_template = self._template_service.get_template(
            selected_code if isinstance(selected_code, str) else None
        )

    def _sync_filter_context(self) -> None:
        company_name = self._active_company_context.company_name or ""
        self._filter_bar.set_company_context(self._current_filter.company_id, company_name)
        self._filter_bar.set_filter(self._current_filter)
        # Keep context strip date pickers in sync
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
            self._review_unmapped_btn.setEnabled(False)
            self._stack.setCurrentIndex(1)
            return

        try:
            report = self._report_service.get_statement(
                self._current_filter,
                self._current_template.template_code,
            )
        except ValidationError as exc:
            show_error(self, "IAS Income Statement Builder", str(exc))
            self._stack.setCurrentIndex(1)
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "IAS Income Statement Builder", str(exc))
            self._stack.setCurrentIndex(1)
            return

        self._current_report = report
        self._update_warning_band(report)
        self._update_summary_strip(report)
        self._review_unmapped_btn.setEnabled(
            self._can_view_unmapped and bool(report.unmapped_relevant_accounts)
        )

        if not report.has_mappings:
            self._stack.setCurrentIndex(2)
            return
        if not report.has_posted_activity:
            self._stack.setCurrentIndex(3)
            return

        self._bind_report(report)
        self._stack.setCurrentIndex(0)

    def _update_warning_band(self, report: IasIncomeStatementReportDTO) -> None:
        if not report.issues:
            self._warning_band.hide()
            return
        error_count = sum(1 for i in report.issues if i.severity_code == "error")
        warning_count = sum(1 for i in report.issues if i.severity_code == "warning")
        parts: list[str] = []
        if error_count:
            parts.append(f"{error_count} error{'s' if error_count != 1 else ''}")
        if warning_count:
            parts.append(f"{warning_count} warning{'s' if warning_count != 1 else ''}")
        total = len(report.issues)
        summary = f"{total} validation issue{'s' if total != 1 else ''}"
        if parts:
            summary = f"{summary} ({', '.join(parts)})"
        self._warning_label.setText(summary)
        self._warning_band.show()

    def _show_warning_issues_dialog(self) -> None:
        if self._current_report is None or not self._current_report.issues:
            return
        issues = self._current_report.issues
        dlg = QDialog(self)
        dlg.setWindowTitle("Validation Issues")
        dlg.setModal(True)
        dlg.resize(540, 380)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QLabel(f"{len(issues)} issue(s) found", dlg)
        header.setObjectName("PageSummary")
        layout.addWidget(header)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        for issue in issues:
            severity_tag = issue.severity_code.upper()
            row_label = QLabel(f"<b>[{severity_tag}]</b> {issue.message}", content)
            row_label.setWordWrap(True)
            row_label.setTextFormat(Qt.TextFormat.RichText)
            content_layout.addWidget(row_label)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        close_box.rejected.connect(dlg.reject)
        layout.addWidget(close_box)
        dlg.exec()

    def _update_summary_strip(self, report: IasIncomeStatementReportDTO) -> None:
        line_lookup = {line.code: line for line in report.lines}
        for code, label in self._summary_values.items():
            line = line_lookup.get(code)
            label.setText(self._fmt(line.signed_amount if line else _ZERO))

    def _bind_report(self, report: IasIncomeStatementReportDTO) -> None:
        template = self._current_template
        self._table.setRowCount(len(report.lines))
        for row_index, line in enumerate(report.lines):
            ref_text = line.code if line.row_kind_code != "group" else ""
            ref_item = QTableWidgetItem(ref_text)
            label_text = line.label
            if line.indent_level > 0:
                label_text = f"{'    ' * line.indent_level}{label_text}"
            label_item = QTableWidgetItem(label_text)
            amount_item = QTableWidgetItem(self._fmt(line.signed_amount or _ZERO))
            amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            ref_item.setData(Qt.ItemDataRole.UserRole, line.code)
            ref_item.setData(Qt.ItemDataRole.UserRole + 1, line.can_drilldown)

            if line.row_kind_code == "group":
                self._apply_row_style(ref_item, label_item, amount_item, template.section_background, True)
            elif line.is_formula:
                self._apply_row_style(ref_item, label_item, amount_item, template.subtotal_background, True)
            else:
                self._apply_row_style(ref_item, label_item, amount_item, template.statement_background, False)

            self._table.setRowHeight(row_index, template.row_height)
            self._table.setItem(row_index, 0, ref_item)
            self._table.setItem(row_index, 1, label_item)
            self._table.setItem(row_index, 2, amount_item)

    def _apply_row_style(
        self,
        ref_item: QTableWidgetItem,
        label_item: QTableWidgetItem,
        amount_item: QTableWidgetItem,
        background_hex: str,
        bold: bool,
    ) -> None:
        background = QColor(background_hex)
        for item in (ref_item, label_item, amount_item):
            item.setBackground(background)
            font = item.font()
            font.setBold(bold)
            font.setPointSize(self._current_template.label_font_size)
            item.setFont(font)
        amount_font = amount_item.font()
        amount_font.setPointSize(self._current_template.amount_font_size)
        amount_font.setBold(bold)
        amount_item.setFont(amount_font)

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if isinstance(company_id, int):
            self._current_filter.company_id = company_id
            self._sync_filter_context()
            self._load_templates()
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
        template_code = self._template_combo.currentData()
        self._current_template = self._template_service.get_template(
            template_code if isinstance(template_code, str) else None
        )
        if isinstance(template_code, str):
            try:
                self._template_service.set_company_template_code(self._current_filter.company_id, template_code)
            except ValidationError as exc:
                show_error(self, "IAS Income Statement Builder", str(exc))
        if self._current_report is not None:
            self._bind_report(self._current_report)

    def _on_template_preview_requested(self, meta: object) -> None:  # noqa: ARG002
        if self._current_report is None:
            return
        IasIncomeStatementTemplatePreviewDialog.show_preview(
            template_dto=self._current_template,
            report_dto=self._current_report,
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
            self, "IAS Income Statement - Statement of Profit or Loss",
        )
        if result is None:
            return
        try:
            export_service = self._service_registry.income_statement_export_service
            export_service.export_ias(
                self._current_report,
                self._current_filter.company_id,
                result,
            )
            result.open_file()
        except Exception as exc:
            show_error(self, "Export Failed", str(exc))

    def _on_manage_mappings(self) -> None:
        company_id = self._current_filter.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            return
        IasIncomeStatementMappingDialog.manage_mappings(
            self._service_registry,
            company_id,
            self._active_company_context.company_name or "Unknown Company",
            parent=self,
        )
        self._load_report()

    def _on_review_unmapped(self) -> None:
        try:
            detail = self._report_service.list_unmapped_accounts(self._current_filter)
        except ValidationError as exc:
            show_error(self, "IAS Income Statement Builder", str(exc))
            return
        IasIncomeStatementLineDetailDialog.open(
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
            show_error(self, "IAS Income Statement Builder", str(exc))
            return
        IasIncomeStatementLineDetailDialog.open(
            service_registry=self._service_registry,
            detail_dto=detail,
            filter_dto=self._current_filter,
            parent=self,
        )

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
        dialog = cls(service_registry, company_id, initial_filter=initial_filter, parent=parent)
        dialog.exec()
