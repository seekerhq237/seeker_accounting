from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.financial_analysis_dto import FinancialAnalysisWorkspaceDTO
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)
from seeker_accounting.modules.reporting.ui.dialogs.analysis_print_preview_dialog import (
    AnalysisPrintPreviewDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.balance_sheet_line_detail_dialog import (
    IasBalanceSheetLineDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.financial_analysis_detail_dialog import (
    FinancialAnalysisDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.ias_income_statement_line_detail_dialog import (
    IasIncomeStatementLineDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.insight_detail_dialog import (
    InsightDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.ohada_income_statement_line_detail_dialog import (
    OhadaIncomeStatementLineDetailDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.ratio_detail_dialog import RatioDetailDialog
from seeker_accounting.modules.reporting.ui.widgets.analysis_section_header import (
    AnalysisSectionHeader,
)
from seeker_accounting.modules.reporting.ui.widgets.insight_card import InsightCard
from seeker_accounting.modules.reporting.ui.widgets.interpretation_panel import (
    InterpretationPanel,
)
from seeker_accounting.modules.reporting.ui.widgets.mini_trend_chart import MiniTrendChart
from seeker_accounting.modules.reporting.ui.widgets.ratio_card import RatioCard
from seeker_accounting.modules.reporting.ui.widgets.reporting_context_strip import (
    ReportingContextStrip,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_empty_state import (
    ReportingEmptyState,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_filter_bar import (
    ReportingFilterBar,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError
from seeker_accounting.shared.ui.message_boxes import show_error
from seeker_accounting.shared.ui.table_helpers import configure_compact_table

_WINDOWS: list["FinancialAnalysisWindow"] = []
_ZERO = Decimal("0.00")


class FinancialAnalysisWindow(QFrame):
    """Slice 14H financial analysis cockpit with premium multi-tab insight views."""

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
        self._workspace_service = service_registry.financial_analysis_workspace_service
        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )
        self._workspace: FinancialAnalysisWorkspaceDTO | None = None
        self._current_filter = ReportingFilterDTO(
            company_id=company_id or self._active_company_context.company_id,
            date_from=initial_filter.date_from if initial_filter else None,
            date_to=initial_filter.date_to if initial_filter else None,
            posted_only=True,
        )

        self.setObjectName("FinancialAnalysisWindow")
        self.setWindowTitle("Financial Analysis & Insights")
        self.setMinimumSize(1095, 675)
        self.setWindowFlag(Qt.WindowType.Window, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_context_strip())
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_content_stack(), 1)

        self._ctx_date_from.dateChanged.connect(self._filter_bar._date_from.setDate)
        self._ctx_date_to.dateChanged.connect(self._filter_bar._date_to.setDate)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._sync_filter_context()

        self._warn_btn = QPushButton("!", self)
        self._warn_btn.setObjectName("HelpButton")
        self._warn_btn.setFixedSize(32, 32)
        self._warn_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._warn_btn.setToolTip("View analysis warnings and limitations")
        self._warn_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._warn_btn.clicked.connect(self._show_warnings_dialog)
        self._warn_btn.hide()
        self._warn_btn.raise_()
        self._warning_messages: tuple[str, ...] = ()

        self._load_workspace()

    def _build_context_strip(self) -> QWidget:
        strip = ReportingContextStrip(self._context_service, self._service_registry, self)
        layout = strip.layout()

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("ToolSep")

        lbl_from = QLabel("From:", self)
        lbl_from.setProperty("role", "caption")
        self._ctx_date_from = QDateEdit(self)
        self._ctx_date_from.setCalendarPopup(True)
        self._ctx_date_from.setDisplayFormat("dd/MM/yyyy")
        self._ctx_date_from.setDate(QDate.currentDate().addMonths(-12))

        lbl_to = QLabel("To:", self)
        lbl_to.setProperty("role", "caption")
        self._ctx_date_to = QDateEdit(self)
        self._ctx_date_to.setCalendarPopup(True)
        self._ctx_date_to.setDisplayFormat("dd/MM/yyyy")
        self._ctx_date_to.setDate(QDate.currentDate())

        pos = layout.count() - 1
        layout.insertWidget(pos, sep); pos += 1
        layout.insertWidget(pos, lbl_from); pos += 1
        layout.insertWidget(pos, self._ctx_date_from); pos += 1
        layout.insertWidget(pos, lbl_to); pos += 1
        layout.insertWidget(pos, self._ctx_date_to)
        return strip

    def _build_filter_bar(self) -> QWidget:
        self._filter_bar = ReportingFilterBar(self)
        self._filter_bar.refresh_requested.connect(self._on_refresh_requested)
        self._filter_bar.print_preview_requested.connect(self._on_print_preview_requested)
        self._filter_bar.template_preview_requested.connect(lambda meta: None)
        self._filter_bar._posted_only.setChecked(True)
        self._filter_bar._posted_only.setEnabled(False)
        self._filter_bar._template_btn.hide()
        fl = self._filter_bar.layout()
        for idx in (3, 2, 1, 0):
            item = fl.itemAt(idx)
            if item and item.widget():
                item.widget().hide()
        return self._filter_bar

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._tabs = QTabWidget(self._stack)
        self._tabs.setObjectName("AnalysisTabHost")
        self._stack.addWidget(self._tabs)
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Active Company",
                message="Select an active company before opening financial analysis.",
                parent=self,
            )
        )
        self._stack.addWidget(
            ReportingEmptyState(
                title="No Financial Analysis Data",
                message="No grounded financial analysis could be assembled for the selected reporting period.",
                parent=self,
            )
        )
        return self._stack

    def _sync_filter_context(self) -> None:
        company_name = self._active_company_context.company_name or ""
        self._filter_bar.set_company_context(self._current_filter.company_id, company_name)
        self._filter_bar.set_filter(self._current_filter)
        self._filter_bar._posted_only.setChecked(True)
        if hasattr(self, "_ctx_date_from") and self._current_filter.date_from:
            d = self._current_filter.date_from
            self._ctx_date_from.setDate(QDate(d.year, d.month, d.day))
        if hasattr(self, "_ctx_date_to") and self._current_filter.date_to:
            d = self._current_filter.date_to
            self._ctx_date_to.setDate(QDate(d.year, d.month, d.day))

    def _load_workspace(self) -> None:
        if not isinstance(self._current_filter.company_id, int) or self._current_filter.company_id <= 0:
            self._workspace = None
            self._tabs.clear()
            self._update_warning_band(())
            self._stack.setCurrentIndex(1)
            return
        try:
            workspace = self._workspace_service.get_workspace(self._current_filter)
        except ValidationError as exc:
            show_error(self, "Financial Analysis & Insights", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Financial Analysis & Insights", str(exc))
            return

        self._workspace = workspace
        messages = tuple(dict.fromkeys((*workspace.warnings, *workspace.limitations)))
        self._update_warning_band(messages)
        self._bind_workspace(workspace)
        self._stack.setCurrentIndex(0 if self._tabs.count() else 2)

    def _bind_workspace(self, workspace: FinancialAnalysisWorkspaceDTO) -> None:
        self._tabs.clear()
        self._add_tab("Overview", "overview", self._build_overview_tab(workspace))
        self._add_tab("Liquidity & Working Capital", "liquidity", self._build_liquidity_tab(workspace))
        self._add_tab("Efficiency & Operating Cycle", "efficiency", self._build_efficiency_tab(workspace))
        self._add_tab("Profitability & Performance", "profitability", self._build_profitability_tab(workspace))
        self._add_tab("Solvency & Capital Structure", "solvency", self._build_solvency_tab(workspace))
        self._add_tab("Trend & Variance", "trend", self._build_trend_tab(workspace))
        self._add_tab("Management Insights", "insights", self._build_management_insights_tab(workspace))

    def _add_tab(self, label: str, section_key: str, widget: QWidget) -> None:
        widget.setProperty("analysisSectionKey", section_key)
        self._tabs.addTab(widget, label)

    def _update_warning_band(self, messages: tuple[str, ...]) -> None:
        self._warning_messages = messages
        self._warn_btn.setVisible(bool(messages))
        self._warn_btn.raise_()

    def _show_warnings_dialog(self) -> None:
        if not self._warning_messages:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Analysis Warnings & Limitations")
        dlg.setMinimumSize(560, 400)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        lbl = QLabel("The following warnings and limitations apply to this analysis:", dlg)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        text = QTextEdit(dlg)
        text.setReadOnly(True)
        text.setPlainText("\n\n".join(f"• {m}" for m in self._warning_messages))
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_warn_btn"):
            self._warn_btn.move(self.width() - 48, self.height() - 48)
            self._warn_btn.raise_()

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        if not isinstance(company_id, int):
            return
        self._current_filter = ReportingFilterDTO(
            company_id=company_id,
            date_from=self._current_filter.date_from,
            date_to=self._current_filter.date_to,
            posted_only=True,
        )
        self._sync_filter_context()
        self._load_workspace()

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
        self._load_workspace()

    def _on_print_preview_requested(self, meta: object) -> None:  # noqa: ARG002
        if self._workspace is None:
            return
        current_widget = self._tabs.currentWidget()
        section_key = current_widget.property("analysisSectionKey") if current_widget is not None else "overview"
        if section_key not in {"overview", "ratios", "insights"}:
            section_key = "ratios" if section_key != "overview" else "overview"
        preview_meta = self._workspace_service.build_print_preview_meta(
            self._workspace,
            "insights" if section_key == "insights" else section_key,
            self._active_company_context.company_name or "Unknown Company",
        )
        AnalysisPrintPreviewDialog.show_preview(preview_meta, parent=self)

    def _open_detail(self, detail_key: str) -> None:
        if self._workspace is None or not detail_key:
            return
        parts = detail_key.split("|")
        try:
            if parts[0] == "ratio" and len(parts) == 2:
                RatioDetailDialog.open(
                    self._workspace_service.build_ratio_detail(self._workspace, parts[1]),
                    detail_opener=self._open_detail,
                    parent=self,
                )
                return
            if parts[0] == "insight" and len(parts) == 2:
                InsightDetailDialog.open(
                    self._workspace_service.build_insight_detail(self._workspace, parts[1]),
                    detail_opener=self._open_detail,
                    parent=self,
                )
                return
            if parts[0] == "trend" and len(parts) == 2:
                FinancialAnalysisDetailDialog.open(
                    self._service_registry.theme_manager,
                    self._workspace_service.build_trend_detail(self._workspace, parts[1]),
                    detail_opener=self._open_detail,
                    parent=self,
                )
                return
            if parts[0] == "bs" and len(parts) == 3:
                as_of_date = date.fromisoformat(parts[2])
                detail = self._service_registry.ias_balance_sheet_service.get_line_detail(
                    ReportingFilterDTO(
                        company_id=self._current_filter.company_id,
                        date_from=None,
                        date_to=as_of_date,
                        posted_only=True,
                    ),
                    parts[1],
                )
                IasBalanceSheetLineDetailDialog.open(self._service_registry, detail, parent=self)
                return
            if parts[0] == "is" and len(parts) == 4:
                filter_dto = ReportingFilterDTO(
                    company_id=self._current_filter.company_id,
                    date_from=date.fromisoformat(parts[2]),
                    date_to=date.fromisoformat(parts[3]),
                    posted_only=True,
                )
                detail = self._service_registry.ias_income_statement_service.get_line_detail(filter_dto, parts[1])
                IasIncomeStatementLineDetailDialog.open(self._service_registry, detail, filter_dto, parent=self)
                return
            if parts[0] == "ohada" and len(parts) == 4:
                filter_dto = ReportingFilterDTO(
                    company_id=self._current_filter.company_id,
                    date_from=date.fromisoformat(parts[2]),
                    date_to=date.fromisoformat(parts[3]),
                    posted_only=True,
                )
                detail = self._service_registry.ohada_income_statement_service.get_line_detail(filter_dto, parts[1])
                OhadaIncomeStatementLineDetailDialog.open(self._service_registry, detail, filter_dto, parent=self)
                return
        except (ValidationError, NotFoundError, ValueError) as exc:
            show_error(self, "Financial Analysis & Insights", str(exc))

    def _build_overview_tab(self, workspace: FinancialAnalysisWorkspaceDTO) -> QWidget:
        page, layout = self._make_tab_page()
        layout.addWidget(
            AnalysisSectionHeader(
                "Financial health snapshot",
                "A compact executive readout of liquidity, profitability, leverage, and cash-cycle position.",
                page,
            )
        )
        self._add_ratio_grid(layout, workspace.overview.headline_ratios, columns=4)
        if workspace.overview.warning_insights:
            layout.addWidget(AnalysisSectionHeader("Watchlist", "Signals requiring management attention.", page))
            self._add_insight_stack(layout, workspace.overview.warning_insights)
        if workspace.overview.strength_insights:
            layout.addWidget(AnalysisSectionHeader("Strengths", "Signals that improved or remained resilient.", page))
            self._add_insight_stack(layout, workspace.overview.strength_insights)
        layout.addStretch(1)
        return page

    def _build_liquidity_tab(self, workspace: FinancialAnalysisWorkspaceDTO) -> QWidget:
        page, layout = self._make_tab_page()
        if workspace.liquidity.interpretation_panel:
            panel = InterpretationPanel(workspace.liquidity.interpretation_panel, page)
            panel.detail_requested.connect(self._open_detail)
            layout.addWidget(panel)
        self._add_ratio_grid(
            layout,
            (
                workspace.liquidity.working_capital_analysis.net_working_capital,
                *workspace.liquidity.liquidity_ratios,
            ),
            columns=4,
        )
        layout.addWidget(AnalysisSectionHeader("Current asset structure", "Composition of liquid and working balances.", page))
        layout.addWidget(
            self._build_table_card(
                "Current assets",
                ("Component", "Amount", "Share"),
                [
                    (row.label, self._fmt_amount(row.amount), self._fmt_share(row.share_percent), row.detail_key)
                    for row in workspace.liquidity.working_capital_analysis.current_asset_rows
                ],
            )
        )
        layout.addWidget(AnalysisSectionHeader("Current liability structure", "Short-term obligations and funding mix.", page))
        layout.addWidget(
            self._build_table_card(
                "Current liabilities",
                ("Component", "Amount", "Share"),
                [
                    (row.label, self._fmt_amount(row.amount), self._fmt_share(row.share_percent), row.detail_key)
                    for row in workspace.liquidity.working_capital_analysis.current_liability_rows
                ],
            )
        )
        if workspace.liquidity.warnings:
            layout.addWidget(self._message_card("Liquidity warnings", workspace.liquidity.warnings))
        layout.addStretch(1)
        return page

    def _build_efficiency_tab(self, workspace: FinancialAnalysisWorkspaceDTO) -> QWidget:
        page, layout = self._make_tab_page()
        if workspace.efficiency.interpretation_panel:
            panel = InterpretationPanel(workspace.efficiency.interpretation_panel, page)
            panel.detail_requested.connect(self._open_detail)
            layout.addWidget(panel)
        self._add_ratio_grid(layout, workspace.efficiency.cycle_ratios, columns=3)
        if workspace.efficiency.warnings:
            layout.addWidget(self._message_card("Operating-cycle notes", workspace.efficiency.warnings))
        layout.addStretch(1)
        return page

    def _build_profitability_tab(self, workspace: FinancialAnalysisWorkspaceDTO) -> QWidget:
        page, layout = self._make_tab_page()
        if workspace.profitability.interpretation_panel:
            panel = InterpretationPanel(workspace.profitability.interpretation_panel, page)
            panel.detail_requested.connect(self._open_detail)
            layout.addWidget(panel)
        self._add_ratio_grid(layout, workspace.profitability.profitability_ratios, columns=3)
        layout.addWidget(AnalysisSectionHeader("Expense structure", "Cost intensity relative to revenue.", page))
        layout.addWidget(
            self._build_table_card(
                "Expense structure",
                ("Component", "Amount", "Share of revenue"),
                [
                    (row.label, self._fmt_amount(row.amount), self._fmt_share(row.share_of_revenue), row.detail_key)
                    for row in workspace.profitability.expense_structure_rows
                ],
            )
        )
        if workspace.profitability.warnings:
            layout.addWidget(self._message_card("Profitability limitations", workspace.profitability.warnings))
        layout.addStretch(1)
        return page

    def _build_solvency_tab(self, workspace: FinancialAnalysisWorkspaceDTO) -> QWidget:
        page, layout = self._make_tab_page()
        if workspace.solvency.interpretation_panel:
            panel = InterpretationPanel(workspace.solvency.interpretation_panel, page)
            panel.detail_requested.connect(self._open_detail)
            layout.addWidget(panel)
        self._add_ratio_grid(layout, workspace.solvency.solvency_ratios, columns=4)
        layout.addWidget(AnalysisSectionHeader("Capital structure mix", "How assets are funded and where leverage sits.", page))
        layout.addWidget(
            self._build_table_card(
                "Capital structure",
                ("Component", "Amount", "Share of assets"),
                [
                    (row.label, self._fmt_amount(row.amount), self._fmt_share(row.share_percent), row.detail_key)
                    for row in workspace.solvency.capital_structure_rows
                ],
            )
        )
        if workspace.solvency.warnings:
            layout.addWidget(self._message_card("Solvency notes", workspace.solvency.warnings))
        layout.addStretch(1)
        return page

    def _build_trend_tab(self, workspace: FinancialAnalysisWorkspaceDTO) -> QWidget:
        page, layout = self._make_tab_page()
        if workspace.trend.interpretation_panel:
            panel = InterpretationPanel(workspace.trend.interpretation_panel, page)
            panel.detail_requested.connect(self._open_detail)
            layout.addWidget(panel)

        layout.addWidget(AnalysisSectionHeader("Mini trend boards", "Compact visuals over the main moving lines.", page))
        trend_grid = QGridLayout()
        trend_grid.setHorizontalSpacing(16)
        trend_grid.setVerticalSpacing(16)
        for index, series in enumerate(workspace.trend.series[:4]):
            trend_grid.addWidget(self._build_series_card(series), index // 2, index % 2)
        layout.addLayout(trend_grid)

        layout.addWidget(AnalysisSectionHeader("Variance analysis", "Current period versus prior period movement.", page))
        layout.addWidget(
            self._build_table_card(
                "Variance analysis",
                ("Metric", "Current", "Prior", "Variance", "Variance %"),
                [
                    (
                        row.label,
                        self._fmt_amount(row.current_value),
                        self._fmt_amount(row.prior_value),
                        self._fmt_amount(row.variance_value),
                        self._fmt_variance_percent(row.variance_percent),
                        row.detail_key,
                    )
                    for row in workspace.trend.variance_rows
                ],
            )
        )
        layout.addWidget(AnalysisSectionHeader("Composition change", "Movement in key balance-sheet components.", page))
        layout.addWidget(
            self._build_table_card(
                "Composition change",
                ("Component", "Current", "Prior", "Variance"),
                [
                    (
                        row.label,
                        self._fmt_amount(row.current_value),
                        self._fmt_amount(row.prior_value),
                        self._fmt_amount(row.variance_value),
                        row.detail_key,
                    )
                    for row in workspace.trend.composition_rows
                ],
            )
        )
        if workspace.trend.warnings:
            layout.addWidget(self._message_card("Trend limitations", workspace.trend.warnings))
        layout.addStretch(1)
        return page

    def _build_management_insights_tab(self, workspace: FinancialAnalysisWorkspaceDTO) -> QWidget:
        page, layout = self._make_tab_page()
        layout.addWidget(
            AnalysisSectionHeader(
                "Ranked management insights",
                "Rule-based executive findings with visible numeric basis and traceable drilldown.",
                page,
            )
        )
        self._add_insight_stack(layout, workspace.management_insights)
        layout.addStretch(1)
        return page

    def _make_tab_page(self) -> tuple[QScrollArea, QVBoxLayout]:
        page = QScrollArea(self._tabs)
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(page)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)
        page.setWidget(content)
        return page, layout

    def _add_ratio_grid(self, layout: QVBoxLayout, ratios, *, columns: int) -> None:
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        for index, ratio in enumerate(ratios):
            card = RatioCard(self._service_registry.theme_manager, ratio, self)
            card.activated.connect(self._open_detail)
            grid.addWidget(card, index // columns, index % columns)
        layout.addLayout(grid)

    def _add_insight_stack(self, layout: QVBoxLayout, insights) -> None:
        for card_dto in insights:
            card = InsightCard(card_dto, self)
            card.activated.connect(self._open_detail)
            layout.addWidget(card)

    def _build_series_card(self, series) -> QWidget:
        card = QFrame(self)
        card.setObjectName("AnalysisRatioCard")
        inner = QVBoxLayout(card)
        inner.setContentsMargins(16, 14, 16, 14)
        inner.setSpacing(8)
        title = QLabel(series.label, card)
        title.setObjectName("AnalysisMetricLabel")
        inner.addWidget(title)
        value = next((point.value for point in reversed(series.points) if point.value is not None), None)
        metric = QLabel(self._fmt_amount(value), card)
        metric.setObjectName("AnalysisMetricValue")
        inner.addWidget(metric)
        chart = MiniTrendChart(self._service_registry.theme_manager, card)
        chart.set_points(series.points, series.color_name)
        inner.addWidget(chart)
        hint = QLabel("Double-click card or use trend detail for a deeper movement review.", card)
        hint.setObjectName("AnalysisInsightMeta")
        hint.setWordWrap(True)
        inner.addWidget(hint)
        card.mouseDoubleClickEvent = lambda event, key=f"trend|{series.metric_code}": self._open_detail(key)  # type: ignore[method-assign]
        return card

    def _build_table_card(self, title: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        title_label = QLabel(title, card)
        title_label.setObjectName("InfoCardTitle")
        layout.addWidget(title_label)
        table = QTableWidget(card)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        configure_compact_table(table)
        table.setSortingEnabled(False)
        table.cellDoubleClicked.connect(lambda row, column, widget=table: self._on_table_double_clicked(widget, row))
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            detail_key = row[-1] if len(row) > len(headers) else None
            values = row[:-1] if len(row) > len(headers) else row
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == 0 and isinstance(detail_key, str) and detail_key:
                    item.setData(Qt.ItemDataRole.UserRole, detail_key)
                if column_index > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_index, column_index, item)
        layout.addWidget(table)
        return card

    def _message_card(self, title: str, messages: tuple[str, ...]) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        heading = QLabel(title, card)
        heading.setObjectName("InfoCardTitle")
        layout.addWidget(heading)
        for message in messages:
            label = QLabel(message, card)
            label.setObjectName("AnalysisInsightMeta")
            label.setWordWrap(True)
            layout.addWidget(label)
        return card

    def _on_table_double_clicked(self, table: QTableWidget, row: int) -> None:
        item = table.item(row, 0)
        if item is None:
            return
        detail_key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(detail_key, str) and detail_key:
            self._open_detail(detail_key)

    @staticmethod
    def _fmt_amount(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.2f}"

    @staticmethod
    def _fmt_share(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{(value * Decimal('100')):,.2f}%"

    @staticmethod
    def _fmt_variance_percent(value: Decimal | None) -> str:
        if value is None:
            return ""
        return f"{value:,.2f}%"

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
        _WINDOWS.append(window)
        window.destroyed.connect(lambda: _WINDOWS.remove(window) if window in _WINDOWS else None)
