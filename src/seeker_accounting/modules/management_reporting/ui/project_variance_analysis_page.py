"""Project Variance Analysis page.

Premium reporting surface that consumes BudgetReportingService to provide
KPI summary, four chart views, and a drilldown variance table for the
selected project.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components import DataTable, DataTableColumn

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.management_reporting.dto.budget_variance_report_dto import (
    ProjectTrendSeriesDTO,
    ProjectVarianceBreakdownItemDTO,
    ProjectVarianceSummaryDTO,
)
from seeker_accounting.modules.management_reporting.ui.variance_chart_widgets import (
    HBarItem,
    HorizontalBarChart,
    TrendLineChart,
    TrendPoint,
    WaterfallChart,
    WaterfallSegment,
)
from seeker_accounting.platform.exceptions import NotFoundError
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.message_boxes import show_error

_ZERO = Decimal(0)


# ── Status threshold helpers ─────────────────────────────────────────────


def _variance_status(variance_amount: Decimal, variance_percent: Decimal | None) -> str:
    """Return a human-readable status label based on variance thresholds."""
    pct = variance_percent or _ZERO
    if variance_amount > 0 and pct >= 5:
        return "On Track"
    if variance_amount >= 0:
        return "Watch"
    if pct > -10:
        return "Over Budget"
    return "Critical"


def _status_color_name(status: str) -> str:
    """Return a QSS-friendly property value for status coloring."""
    return {
        "On Track": "success",
        "Watch": "warning",
        "Over Budget": "danger",
        "Critical": "danger",
    }.get(status, "")


# ── Amount formatting ────────────────────────────────────────────────────


def _fmt(v: Decimal | None, dash: str = "—") -> str:
    if v is None:
        return dash
    return f"{v:,.2f}"


def _fmt_pct(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.1f}%"


# ======================================================================
# Project Variance Analysis Page
# ======================================================================


class ProjectVarianceAnalysisPage(QWidget):
    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._summary: ProjectVarianceSummaryDTO | None = None
        self._breakdown_items: list[ProjectVarianceBreakdownItemDTO] = []
        self._trend: ProjectTrendSeriesDTO | None = None

        self.setObjectName("ProjectVarianceAnalysisPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_content_stack(), 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._on_company_changed
        )
        self._service_registry.navigation_service.navigation_context_changed.connect(
            self._on_navigation_context_changed
        )

        self._load_projects()

    # ------------------------------------------------------------------
    # Toolbar (project selector)
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")
        card.setProperty("card", True)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        # Project selector
        proj_block = QWidget(card)
        proj_layout = QVBoxLayout(proj_block)
        proj_layout.setContentsMargins(0, 0, 0, 0)
        proj_layout.setSpacing(2)

        proj_caption = QLabel("Project", proj_block)
        proj_caption.setProperty("role", "caption")
        proj_layout.addWidget(proj_caption)

        self._project_combo = QComboBox(proj_block)
        self._project_combo.setMinimumWidth(240)
        self._project_combo.currentIndexChanged.connect(self._on_project_changed)
        proj_layout.addWidget(self._project_combo)

        layout.addWidget(proj_block)

        # Dimension view toggle
        dim_block = QWidget(card)
        dim_layout = QVBoxLayout(dim_block)
        dim_layout.setContentsMargins(0, 0, 0, 0)
        dim_layout.setSpacing(2)

        dim_caption = QLabel("Drill-down view", dim_block)
        dim_caption.setProperty("role", "caption")
        dim_layout.addWidget(dim_caption)

        self._dimension_combo = QComboBox(dim_block)
        self._dimension_combo.addItems(["By Cost Code", "By Job"])
        self._dimension_combo.currentIndexChanged.connect(self._on_dimension_changed)
        dim_layout.addWidget(self._dimension_combo)

        layout.addWidget(dim_block)

        layout.addStretch(1)

        # Status chip
        self._status_chip = QLabel(card)
        self._status_chip.setObjectName("VarianceStatusChip")
        self._status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_chip.setFixedHeight(28)
        self._status_chip.setMinimumWidth(90)
        self._status_chip.setStyleSheet(
            "QLabel#VarianceStatusChip { padding: 4px 12px; border-radius: 6px; font-weight: 600; font-size: 12px; }"
        )
        layout.addWidget(self._status_chip)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self._reload_analysis)
        layout.addWidget(self._refresh_button)

        return card

    # ------------------------------------------------------------------
    # Content stack
    # ------------------------------------------------------------------

    def _build_content_stack(self) -> QWidget:
        self._stack = QStackedWidget(self)
        self._analysis_surface = self._build_analysis_surface()
        self._empty_state = build_empty_state("management_reporting.project_variance.no_selection", parent=self)
        self._no_company_state = build_empty_state("management_reporting.no_company", parent=self)
        self._stack.addWidget(self._analysis_surface)
        self._stack.addWidget(self._empty_state)
        self._stack.addWidget(self._no_company_state)
        return self._stack

    # ------------------------------------------------------------------
    # Analysis surface (scrollable)
    # ------------------------------------------------------------------

    def _build_analysis_surface(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_kpi_band(content))
        layout.addWidget(self._build_charts_row(content))
        layout.addWidget(self._build_drilldown_table(content))

        scroll.setWidget(content)
        return scroll

    # ------------------------------------------------------------------
    # KPI summary band (9 metrics)
    # ------------------------------------------------------------------

    def _build_kpi_band(self, parent: QWidget) -> QWidget:
        card = QFrame(parent)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        title = QLabel("Project Control Summary", card)
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        # 3 rows x 3 metrics
        self._kpi_labels: dict[str, QLabel] = {}

        metrics = [
            [
                ("Approved Budget", "approved_budget"),
                ("Actual Cost", "actual_cost"),
                ("Variance", "variance"),
            ],
            [
                ("Commitments", "commitments"),
                ("Exposure (Cost + Commit.)", "exposure"),
                ("Remaining Budget", "remaining"),
            ],
            [
                ("Billed Revenue", "revenue"),
                ("Margin", "margin"),
                ("Margin %", "margin_pct"),
            ],
        ]

        for row_metrics in metrics:
            row_widget = QWidget(card)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(16)

            for label_text, key in row_metrics:
                block = QWidget(row_widget)
                block_layout = QVBoxLayout(block)
                block_layout.setContentsMargins(0, 0, 0, 0)
                block_layout.setSpacing(1)

                caption = QLabel(label_text, block)
                caption.setProperty("role", "caption")
                block_layout.addWidget(caption)

                value = QLabel("—", block)
                value.setObjectName("ToolbarValue")
                block_layout.addWidget(value)

                self._kpi_labels[key] = value
                row_layout.addWidget(block, 1)

            layout.addWidget(row_widget)

        return card

    # ------------------------------------------------------------------
    # Charts row
    # ------------------------------------------------------------------

    def _build_charts_row(self, parent: QWidget) -> QWidget:
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        palette = self._service_registry.theme_manager.current_palette

        # Top row: waterfall + variance bars
        top_row = QWidget(container)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)

        waterfall_card = QFrame(top_row)
        waterfall_card.setObjectName("PageCard")
        wf_layout = QVBoxLayout(waterfall_card)
        wf_layout.setContentsMargins(14, 10, 14, 10)
        self._waterfall_chart = WaterfallChart(palette, waterfall_card)
        self._waterfall_chart.setMinimumHeight(220)
        wf_layout.addWidget(self._waterfall_chart)
        top_layout.addWidget(waterfall_card, 1)

        bars_card = QFrame(top_row)
        bars_card.setObjectName("PageCard")
        bars_layout = QVBoxLayout(bars_card)
        bars_layout.setContentsMargins(14, 10, 14, 10)
        self._hbar_chart = HorizontalBarChart(palette, bars_card)
        self._hbar_chart.setMinimumHeight(220)
        bars_layout.addWidget(self._hbar_chart)
        top_layout.addWidget(bars_card, 1)

        layout.addWidget(top_row)

        # Bottom row: trend chart (full width)
        trend_card = QFrame(container)
        trend_card.setObjectName("PageCard")
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(14, 10, 14, 10)
        self._trend_chart = TrendLineChart(palette, trend_card)
        self._trend_chart.setMinimumHeight(200)
        trend_layout.addWidget(self._trend_chart)

        layout.addWidget(trend_card)

        # Connect theme changes
        self._service_registry.theme_manager.theme_changed.connect(self._on_theme_changed)

        return container

    # ------------------------------------------------------------------
    # Drilldown table
    # ------------------------------------------------------------------

    def _build_drilldown_table(self, parent: QWidget) -> QWidget:
        card = QFrame(parent)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        top_row = QWidget(card)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)

        self._table_title = QLabel("Variance Breakdown", top_row)
        self._table_title.setObjectName("CardTitle")
        top_layout.addWidget(self._table_title)

        top_layout.addStretch(1)

        self._table_count_label = QLabel(top_row)
        self._table_count_label.setObjectName("ToolbarMeta")
        top_layout.addWidget(self._table_count_label)

        layout.addWidget(top_row)

        self._variance_model = QStandardItemModel(0, 8, card)
        self._variance_model.setHorizontalHeaderLabels([
            "Dimension", "Budget", "Actual Cost", "Commitments",
            "Exposure", "Remaining", "Variance", "Status",
        ])
        self._variance_table = DataTable(
            columns=(
                DataTableColumn(key="dimension", title="Dimension"),
                DataTableColumn(key="budget", title="Budget"),
                DataTableColumn(key="actual_cost", title="Actual Cost"),
                DataTableColumn(key="commitments", title="Commitments"),
                DataTableColumn(key="exposure", title="Exposure"),
                DataTableColumn(key="remaining", title="Remaining"),
                DataTableColumn(key="variance", title="Variance"),
                DataTableColumn(key="status", title="Status"),
            ),
            show_search=False,
            parent=card,
        )
        self._variance_table.set_model(self._variance_model)
        layout.addWidget(self._variance_table)
        return card

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def _load_projects(self) -> None:
        self._project_combo.blockSignals(True)
        self._project_combo.clear()

        active = self._active_company()
        if active is None:
            self._project_combo.blockSignals(False)
            self._stack.setCurrentWidget(self._no_company_state)
            return

        try:
            projects = self._service_registry.project_service.list_projects(active.company_id)
        except Exception as exc:
            self._project_combo.blockSignals(False)
            self._stack.setCurrentWidget(self._empty_state)
            show_error(self, "Projects", f"Could not load projects.\n\n{exc}")
            return

        if not projects:
            self._project_combo.addItem("No projects available", None)
            self._project_combo.blockSignals(False)
            self._stack.setCurrentWidget(self._empty_state)
            return

        for proj in projects:
            self._project_combo.addItem(
                f"{proj.project_code} — {proj.project_name}",
                proj.id,
            )

        self._project_combo.blockSignals(False)
        self._apply_navigation_context()
        self._on_project_changed()

    def _reload_analysis(self) -> None:
        self._on_project_changed()

    def _on_company_changed(self) -> None:
        self._load_projects()

    def _on_navigation_context_changed(self, nav_id: str, context: object) -> None:
        _ = context
        if nav_id != nav_ids.PROJECT_VARIANCE_ANALYSIS:
            return
        self._apply_navigation_context()

    def _apply_navigation_context(self) -> None:
        context = self._service_registry.navigation_service.current_navigation_context
        project_id = context.get("project_id")
        if not isinstance(project_id, int):
            return
        for index in range(self._project_combo.count()):
            if self._project_combo.itemData(index) == project_id:
                self._project_combo.setCurrentIndex(index)
                return

    def _on_project_changed(self) -> None:
        project_id = self._project_combo.currentData()
        if project_id is None:
            self._clear_analysis()
            self._stack.setCurrentWidget(self._empty_state)
            return

        active = self._active_company()
        if active is None:
            return

        try:
            self._summary = self._service_registry.budget_reporting_service.get_project_variance_summary(
                active.company_id, project_id
            )
        except NotFoundError:
            self._clear_analysis()
            self._stack.setCurrentWidget(self._empty_state)
            return
        except Exception as exc:
            self._clear_analysis()
            show_error(self, "Variance Analysis", f"Could not load variance data.\n\n{exc}")
            return

        self._populate_kpis()
        self._populate_waterfall()
        self._load_breakdown()
        self._load_trend(active.company_id, project_id)
        self._stack.setCurrentWidget(self._analysis_surface)

    def _on_dimension_changed(self) -> None:
        self._load_breakdown()

    # ------------------------------------------------------------------
    # KPI population
    # ------------------------------------------------------------------

    def _populate_kpis(self) -> None:
        s = self._summary
        if s is None:
            return

        palette = self._service_registry.theme_manager.current_palette
        status = _variance_status(s.variance_amount, s.variance_percent)

        self._kpi_labels["approved_budget"].setText(_fmt(s.approved_budget_amount))
        self._kpi_labels["actual_cost"].setText(_fmt(s.actual_cost_amount))

        # Variance with color
        v_label = self._kpi_labels["variance"]
        v_text = f"{_fmt(s.variance_amount)}  ({_fmt_pct(s.variance_percent)})"
        v_label.setText(v_text)
        if s.variance_amount >= 0:
            v_label.setStyleSheet(f"color: {palette.success};")
        else:
            v_label.setStyleSheet(f"color: {palette.danger};")

        self._kpi_labels["commitments"].setText(_fmt(s.approved_commitment_amount))
        self._kpi_labels["exposure"].setText(_fmt(s.total_exposure_amount))
        self._kpi_labels["remaining"].setText(_fmt(s.remaining_budget_after_commitments_amount))
        self._kpi_labels["revenue"].setText(_fmt(s.billed_revenue_amount))
        self._kpi_labels["margin"].setText(_fmt(s.margin_amount))
        self._kpi_labels["margin_pct"].setText(_fmt_pct(s.margin_percent))

        # Status chip
        self._update_status_chip(status, palette)

    def _update_status_chip(self, status: str, palette: object) -> None:
        color_map = {
            "On Track": (palette.status_success_fg, palette.status_success_bg),
            "Watch": (palette.status_warning_fg, palette.status_warning_bg),
            "Over Budget": (palette.status_danger_fg, palette.status_danger_bg),
            "Critical": (palette.status_danger_fg, palette.status_danger_bg),
        }
        fg, bg = color_map.get(status, (palette.text_primary, palette.secondary_surface))
        self._status_chip.setText(status)
        self._status_chip.setStyleSheet(
            f"QLabel#VarianceStatusChip {{ color: {fg}; background: {bg}; "
            f"padding: 4px 12px; border-radius: 6px; font-weight: 600; font-size: 12px; }}"
        )

    # ------------------------------------------------------------------
    # Waterfall chart
    # ------------------------------------------------------------------

    def _populate_waterfall(self) -> None:
        s = self._summary
        if s is None:
            return

        segments = [
            WaterfallSegment("Budget", s.approved_budget_amount, is_total=True),
            WaterfallSegment("Actual Cost", -s.actual_cost_amount),
            WaterfallSegment("Commitments", -s.approved_commitment_amount),
            WaterfallSegment("Remaining", s.remaining_budget_after_commitments_amount, is_total=True),
        ]
        self._waterfall_chart.set_data(segments, "Budget Control Bridge")

    # ------------------------------------------------------------------
    # Breakdown (dimension-specific)
    # ------------------------------------------------------------------

    def _load_breakdown(self) -> None:
        s = self._summary
        if s is None:
            return

        active = self._active_company()
        if active is None:
            return

        by_job = self._dimension_combo.currentIndex() == 1
        try:
            if by_job:
                self._breakdown_items = self._service_registry.budget_reporting_service.get_project_variance_by_job(
                    active.company_id, s.project_id
                )
                self._table_title.setText("Variance by Job")
            else:
                self._breakdown_items = self._service_registry.budget_reporting_service.get_project_variance_by_cost_code(
                    active.company_id, s.project_id
                )
                self._table_title.setText("Variance by Cost Code")
        except Exception as exc:
            self._breakdown_items = []
            show_error(self, "Breakdown", f"Could not load breakdown.\n\n{exc}")
            return

        self._populate_breakdown_table(by_job)
        self._populate_hbar_chart(by_job)

    @staticmethod
    def _make_item(text: str, *, right_align: bool = False) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if right_align:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    def _populate_breakdown_table(self, by_job: bool) -> None:
        self._variance_model.removeRows(0, self._variance_model.rowCount())

        palette = self._service_registry.theme_manager.current_palette

        for item in self._breakdown_items:
            if by_job:
                dim_label = f"{item.project_job_code or '—'} — {item.project_job_name or '—'}"
            else:
                dim_label = f"{item.project_cost_code or '—'} — {item.project_cost_code_name or '—'}"

            status = _variance_status(item.variance_amount, item.variance_percent)

            variance_item = self._make_item(
                f"{_fmt(item.variance_amount)}  ({_fmt_pct(item.variance_percent)})",
                right_align=True,
            )
            if item.variance_amount >= 0:
                variance_item.setForeground(QBrush(QColor(palette.success)))
            else:
                variance_item.setForeground(QBrush(QColor(palette.danger)))

            status_item = self._make_item(status)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            color_name = _status_color_name(status)
            if color_name == "success":
                status_item.setForeground(QBrush(QColor(palette.success)))
            elif color_name == "warning":
                status_item.setForeground(QBrush(QColor(palette.warning)))
            elif color_name == "danger":
                status_item.setForeground(QBrush(QColor(palette.danger)))

            self._variance_model.appendRow([
                self._make_item(dim_label),
                self._make_item(_fmt(item.approved_budget_amount), right_align=True),
                self._make_item(_fmt(item.actual_cost_amount), right_align=True),
                self._make_item(_fmt(item.approved_commitment_amount), right_align=True),
                self._make_item(_fmt(item.total_exposure_amount), right_align=True),
                self._make_item(_fmt(item.remaining_budget_amount), right_align=True),
                variance_item,
                status_item,
            ])

        n = len(self._breakdown_items)
        self._table_count_label.setText(f"{n} item{'s' if n != 1 else ''}")

    def _populate_hbar_chart(self, by_job: bool) -> None:
        items: list[HBarItem] = []
        for bd in self._breakdown_items[:12]:  # top 12
            if by_job:
                label = bd.project_job_code or "—"
            else:
                label = bd.project_cost_code or "—"
            items.append(HBarItem(
                label=label,
                value=bd.variance_amount,
                secondary_value=bd.approved_commitment_amount,
            ))

        title = "Variance by Job" if by_job else "Variance by Cost Code"
        self._hbar_chart.set_data(items, title)

    # ------------------------------------------------------------------
    # Trend chart
    # ------------------------------------------------------------------

    def _load_trend(self, company_id: int, project_id: int) -> None:
        try:
            self._trend = self._service_registry.budget_reporting_service.get_chart_trend_series(
                company_id, project_id
            )
        except NotFoundError:
            self._trend = None
            return
        except Exception:
            self._trend = None
            return

        if self._trend is None or not self._trend.points:
            self._trend_chart.set_data([], None)
            return

        points = [
            TrendPoint(
                label=p.period_label,
                actual_cumulative=p.cumulative_actual_cost_amount,
                revenue_cumulative=p.cumulative_billed_revenue_amount,
            )
            for p in self._trend.points
        ]
        self._trend_chart.set_data(
            points,
            budget_reference=self._trend.current_budget_amount,
            title=f"Cost & Revenue Trend — {self._trend.project_code}",
        )

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _on_theme_changed(self, _theme_name: str) -> None:
        palette = self._service_registry.theme_manager.current_palette
        self._waterfall_chart.update_palette(palette)
        self._hbar_chart.update_palette(palette)
        self._trend_chart.update_palette(palette)
        # Re-populate to update colors in KPIs and table cells
        if self._summary is not None:
            self._populate_kpis()
            by_job = self._dimension_combo.currentIndex() == 1
            self._populate_breakdown_table(by_job)

    # ------------------------------------------------------------------
    # Clear / utility
    # ------------------------------------------------------------------

    def _clear_analysis(self) -> None:
        self._summary = None
        self._breakdown_items = []
        self._trend = None
        for lbl in self._kpi_labels.values():
            lbl.setText("—")
            lbl.setStyleSheet("")
        self._status_chip.setText("")
        self._status_chip.setStyleSheet(
            "QLabel#VarianceStatusChip { padding: 4px 12px; border-radius: 6px; font-weight: 600; font-size: 12px; }"
        )
        self._waterfall_chart.set_data([])
        self._hbar_chart.set_data([])
        self._trend_chart.set_data([])
        self._variance_model.removeRows(0, self._variance_model.rowCount())
        self._table_count_label.setText("")
