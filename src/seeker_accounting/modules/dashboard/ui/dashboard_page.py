from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QBrush, QCursor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QGridLayout,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.modules.companies.dto.company_dto import ActiveCompanyDTO
from seeker_accounting.modules.dashboard.dto.dashboard_dto import (
    DashboardAgingSnapshotDTO,
    DashboardAttentionItemDTO,
    DashboardCashLiquidityDTO,
    DashboardDataDTO,
    DashboardKpiDeltaDTO,
    DashboardKpiDTO,
    DashboardRecentActivityItemDTO,
    DashboardSetupChecklistDTO,
)
from seeker_accounting.shared.ui.entity_detail.money_bar import MoneyBar, MoneyBarItem
from seeker_accounting.shared.ui.components import DataTable, DataTableColumn
from seeker_accounting.shared.services.telemetry_service import get_default_telemetry_service
from seeker_accounting.shared.ui.accessibility import describe_button, set_accessible_metadata
from seeker_accounting.shared.ui.coach_marks import install_coach_mark
from seeker_accounting.shared.ui.empty_states import build_empty_state
from seeker_accounting.shared.ui.keyboard_shortcuts import install_shortcut, shortcut_map
from seeker_accounting.shared.ui.styles.palette import DARK_PALETTE, LIGHT_PALETTE

_log = logging.getLogger(__name__)

_DOC_TYPE_LABELS = {
    "journal": "Journal",
    "invoice": "Invoice",
    "bill": "Bill",
    "receipt": "Receipt",
    "payment": "Payment",
}

_ACCT_TYPE_LABELS = {
    "bank": "Bank",
    "cash": "Cash",
    "mobile_money": "Mobile Money",
    "savings": "Savings",
    "credit_card": "Credit Card",
}


class DashboardPage(QWidget):
    """Production dashboard - KPI strip, tabs (Overview / Cash & Liquidity), activity, aging."""

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._telemetry = get_default_telemetry_service()
        self._data: DashboardDataDTO | None = None
        self.setObjectName("DashboardPage")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._page_stack = QStackedWidget(self)
        self._main_surface = self._build_main_surface()
        self._no_company_surface = self._build_no_company_surface()
        self._page_stack.addWidget(self._main_surface)
        self._page_stack.addWidget(self._no_company_surface)
        root_layout.addWidget(self._page_stack)

        self._service_registry.active_company_context.active_company_changed.connect(
            self._on_company_changed
        )
        self._install_shortcuts()
        self._reload_dashboard()

    def _install_shortcuts(self) -> None:
        specs = shortcut_map("dashboard")
        if refresh := specs.get("refresh"):
            install_shortcut(self, refresh, self._reload_dashboard)
        if overview := specs.get("open_overview"):
            install_shortcut(self, overview, lambda: self._tab_bar.setCurrentIndex(0))
        if cash := specs.get("open_cash"):
            install_shortcut(self, cash, lambda: self._tab_bar.setCurrentIndex(1))

    def _build_main_surface(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("DashboardContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)

        self._context_row = self._build_context_row(container)
        layout.addWidget(self._context_row)

        self._money_bar = MoneyBar(container)
        layout.addWidget(self._money_bar)

        tab_wrapper = QWidget(container)
        tab_wrapper.setObjectName("DashboardTabWrapper")
        tab_wrapper_layout = QVBoxLayout(tab_wrapper)
        tab_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        tab_wrapper_layout.setSpacing(0)

        self._tab_bar = QTabBar(tab_wrapper)
        self._tab_bar.setObjectName("DashboardTabBar")
        self._tab_bar.setExpanding(False)
        self._tab_bar.setDrawBase(False)
        self._tab_bar.addTab("Overview")
        self._tab_bar.addTab("Cash & Liquidity")
        tab_wrapper_layout.addWidget(self._tab_bar)

        self._tab_stack = QStackedWidget(tab_wrapper)
        self._tab_stack.setObjectName("DashboardTabStack")
        self._overview_tab = self._build_overview_tab(self._tab_stack)
        self._cash_tab = self._build_cash_tab(self._tab_stack)
        self._tab_stack.addWidget(self._overview_tab)
        self._tab_stack.addWidget(self._cash_tab)
        tab_wrapper_layout.addWidget(self._tab_stack)

        self._tab_bar.currentChanged.connect(self._tab_stack.setCurrentIndex)
        layout.addWidget(tab_wrapper, 1)

        scroll.setWidget(container)
        return scroll

    def _build_no_company_surface(self) -> QWidget:
        outer = QWidget(self)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(20, 20, 20, 20)
        outer_layout.addStretch(1)

        card = build_empty_state("dashboard.no_company", parent=outer)
        card.setObjectName("DashboardNoCompanyCard")
        card.primary_clicked.connect(lambda: self._navigate_to(nav_ids.COMPANIES))

        outer_layout.addWidget(card)
        outer_layout.addStretch(2)
        return outer

    def _build_context_row(self, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        row.setObjectName("DashboardContextRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._context_label = QLabel("", row)
        self._context_label.setObjectName("DashboardContextLabel")
        layout.addWidget(self._context_label)
        layout.addStretch(1)

        refresh_btn = QPushButton("Refresh", row)
        refresh_btn.setObjectName("DashboardRefreshButton")
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        describe_button(refresh_btn, "Refresh dashboard", "Reload dashboard data for the active company.")
        refresh_btn.clicked.connect(self._reload_dashboard)
        layout.addWidget(refresh_btn)

        return row

    def _create_panel(
        self,
        parent: QWidget,
        title_text: str,
        coach_mark_key: str | None = None,
    ) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
        panel = QFrame(parent)
        panel.setObjectName("Panel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame(panel)
        header.setObjectName("PanelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title = QLabel(title_text, header)
        title.setObjectName("PanelHeaderTitle")
        if coach_mark_key:
            install_coach_mark(title, coach_mark_key)
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        outer.addWidget(header)

        body = QWidget(panel)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 10, 12, 12)
        body_layout.setSpacing(8)
        outer.addWidget(body)

        return panel, body_layout, header_layout

    def _build_overview_tab(self, parent: QWidget) -> QWidget:
        widget = QWidget(parent)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(14)

        left = QWidget(widget)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        self._setup_checklist_panel = self._build_setup_checklist_panel(left)
        left_layout.addWidget(self._setup_checklist_panel)
        self._activity_panel = self._build_activity_panel(left)
        left_layout.addWidget(self._activity_panel)
        self._attention_panel = self._build_attention_panel(left)
        left_layout.addWidget(self._attention_panel)
        left_layout.addStretch(1)

        right = QWidget(widget)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)
        self._ar_aging_panel = self._build_aging_panel(right, "Receivables Aging")
        right_layout.addWidget(self._ar_aging_panel)
        self._ap_aging_panel = self._build_aging_panel(right, "Payables Aging")
        right_layout.addWidget(self._ap_aging_panel)
        self._quick_actions_panel = self._build_quick_actions_panel(right)
        right_layout.addWidget(self._quick_actions_panel)
        right_layout.addStretch(1)

        layout.addWidget(left, 3)
        layout.addWidget(right, 2)
        return widget

    def _build_activity_panel(self, parent: QWidget) -> QWidget:
        panel, layout, _header_layout = self._create_panel(parent, "Recent Activity")

        self._activity_model = QStandardItemModel(0, 5, panel)
        self._activity_model.setHorizontalHeaderLabels(["Date", "Document", "Description", "Amount", "Status"])
        self._activity_table = DataTable(
            columns=(
                DataTableColumn(key="date", title="Date"),
                DataTableColumn(key="document", title="Document"),
                DataTableColumn(key="description", title="Description"),
                DataTableColumn(key="amount", title="Amount"),
                DataTableColumn(key="status", title="Status"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=panel,
        )
        self._activity_table.set_model(self._activity_model)
        self._activity_table.setMinimumHeight(180)
        self._activity_table.setMaximumHeight(360)
        self._activity_table.view().doubleClicked.connect(self._on_activity_double_clicked)

        self._activity_empty = build_empty_state("dashboard.recent_activity", parent=panel)
        self._activity_empty.setMinimumHeight(92)
        self._activity_empty.setMaximumHeight(140)

        layout.addWidget(self._activity_table)
        layout.addWidget(self._activity_empty)
        self._activity_empty.setVisible(False)
        return panel

    def _build_attention_panel(self, parent: QWidget) -> QWidget:
        panel, layout, _header_layout = self._create_panel(
            parent,
            "Requires Attention",
            coach_mark_key="term.pending_postings",
        )

        self._attention_container = QWidget(panel)
        self._attention_layout = QVBoxLayout(self._attention_container)
        self._attention_layout.setContentsMargins(0, 4, 0, 0)
        self._attention_layout.setSpacing(2)
        layout.addWidget(self._attention_container)

        self._attention_empty = build_empty_state("dashboard.attention", parent=panel)
        self._attention_empty.setMinimumHeight(90)
        self._attention_empty.setMaximumHeight(130)
        layout.addWidget(self._attention_empty)
        self._attention_empty.setVisible(False)
        return panel

    def _build_setup_checklist_panel(self, parent: QWidget) -> QWidget:
        panel, layout, _header_layout = self._create_panel(
            parent,
            "Setup Checklist",
            coach_mark_key="term.setup_checklist",
        )
        self._setup_summary_label = QLabel("", panel)
        self._setup_summary_label.setObjectName("DashboardSetupSummary")
        set_accessible_metadata(
            self._setup_summary_label,
            "Setup checklist progress",
            "Shows how many setup tasks are complete for the active company.",
        )
        layout.addWidget(self._setup_summary_label)

        self._setup_items_container = QWidget(panel)
        self._setup_items_layout = QVBoxLayout(self._setup_items_container)
        self._setup_items_layout.setContentsMargins(0, 0, 0, 0)
        self._setup_items_layout.setSpacing(4)
        layout.addWidget(self._setup_items_container)
        return panel

    def _build_aging_panel(self, parent: QWidget, title_text: str) -> QFrame:
        panel, layout, _header_layout = self._create_panel(
            parent,
            title_text,
            coach_mark_key="term.aging",
        )

        bar = AgingBar(panel)
        bar.setFixedHeight(14)
        layout.addWidget(bar)

        buckets_widget = QWidget(panel)
        buckets_layout = QGridLayout(buckets_widget)
        buckets_layout.setContentsMargins(0, 4, 0, 0)
        buckets_layout.setHorizontalSpacing(6)
        buckets_layout.setVerticalSpacing(2)

        bucket_labels = ("Current", "1-30d", "31-60d", "61-90d", "91d+")
        value_labels: list[QLabel] = []
        for col, lbl_text in enumerate(bucket_labels):
            lbl = QLabel(lbl_text, buckets_widget)
            lbl.setObjectName("DashboardAgingBucketLabel")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            buckets_layout.addWidget(lbl, 0, col)

            val = QLabel("-", buckets_widget)
            val.setObjectName("DashboardAgingBucketValue")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            buckets_layout.addWidget(val, 1, col)
            value_labels.append(val)

        layout.addWidget(buckets_widget)

        total_row = QWidget(panel)
        total_layout = QHBoxLayout(total_row)
        total_layout.setContentsMargins(0, 4, 0, 0)
        total_layout.setSpacing(6)
        total_lbl = QLabel("Total", total_row)
        total_lbl.setObjectName("DashboardAgingBucketLabel")
        total_layout.addWidget(total_lbl)
        total_layout.addStretch(1)
        total_val = QLabel("-", total_row)
        total_val.setObjectName("DashboardAgingTotal")
        total_layout.addWidget(total_val)
        layout.addWidget(total_row)

        panel.setProperty("_aging_bar", bar)
        panel.setProperty("_aging_values", value_labels)
        panel.setProperty("_aging_total", total_val)
        return panel

    def _build_quick_actions_panel(self, parent: QWidget) -> QWidget:
        panel, layout, _header_layout = self._create_panel(parent, "Quick Actions")

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        actions = [
            ("New Journal Entry", nav_ids.JOURNALS),
            ("New Invoice", nav_ids.SALES_INVOICES),
            ("New Receipt", nav_ids.CUSTOMER_RECEIPTS),
            ("New Bill", nav_ids.PURCHASE_BILLS),
            ("Supplier Payment", nav_ids.SUPPLIER_PAYMENTS),
            ("New Item", nav_ids.ITEMS),
        ]

        for idx, (label, target_nav_id) in enumerate(actions):
            btn = QPushButton(label, panel)
            btn.setObjectName("DashboardQuickAction")
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            describe_button(btn, label, f"Open {label.lower()} workflow.")
            btn.clicked.connect(lambda checked=False, nid=target_nav_id: self._navigate_to(nid))
            grid.addWidget(btn, idx // 3, idx % 3)

        layout.addLayout(grid)
        return panel

    def _build_cash_tab(self, parent: QWidget) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(14)

        self._balance_strip = self._build_balance_strip(widget)
        layout.addWidget(self._balance_strip)

        # Cash trend chart panel
        trend_panel, tp_layout, th_layout = self._create_panel(
            widget,
            "Daily Inflow vs Outflow",
            coach_mark_key="term.cash_liquidity",
        )

        # Legend
        inflow_swatch = QLabel(trend_panel)
        inflow_swatch.setObjectName("DashboardTrendLegendInflow")
        inflow_swatch.setFixedSize(10, 10)
        th_layout.addWidget(inflow_swatch)
        inflow_lbl = QLabel("Inflow", trend_panel)
        inflow_lbl.setObjectName("DashboardTrendLegendLabel")
        th_layout.addWidget(inflow_lbl)

        outflow_swatch = QLabel(trend_panel)
        outflow_swatch.setObjectName("DashboardTrendLegendOutflow")
        outflow_swatch.setFixedSize(10, 10)
        th_layout.addWidget(outflow_swatch)
        outflow_lbl = QLabel("Outflow", trend_panel)
        outflow_lbl.setObjectName("DashboardTrendLegendLabel")
        th_layout.addWidget(outflow_lbl)

        self._trend_chart = TrendChart(trend_panel)
        self._trend_chart.setMinimumHeight(140)
        tp_layout.addWidget(self._trend_chart)

        self._trend_empty = build_empty_state("dashboard.cash_movements", parent=trend_panel)
        self._trend_empty.setMinimumHeight(92)
        self._trend_empty.setMaximumHeight(140)
        self._trend_empty.setVisible(False)
        tp_layout.addWidget(self._trend_empty)

        layout.addWidget(trend_panel)

        accounts_panel, ap_layout, _header_layout = self._create_panel(
            widget,
            "Financial Account Balances",
        )

        self._accounts_model = QStandardItemModel(0, 3, accounts_panel)
        self._accounts_model.setHorizontalHeaderLabels(["Account", "Type", "Balance"])
        self._accounts_table = DataTable(
            columns=(
                DataTableColumn(key="account", title="Account"),
                DataTableColumn(key="type", title="Type"),
                DataTableColumn(key="balance", title="Balance"),
            ),
            show_search=False,
            show_count=False,
            show_density_toggle=False,
            show_column_chooser=False,
            parent=accounts_panel,
        )
        self._accounts_table.set_model(self._accounts_model)

        self._accounts_empty = build_empty_state("dashboard.financial_accounts", parent=accounts_panel)
        self._accounts_empty.setMinimumHeight(92)
        self._accounts_empty.setMaximumHeight(140)

        ap_layout.addWidget(self._accounts_table)
        ap_layout.addWidget(self._accounts_empty)
        self._accounts_empty.setVisible(False)

        layout.addWidget(accounts_panel)
        layout.addStretch(1)
        return widget

    def _build_balance_strip(self, parent: QWidget) -> QWidget:
        strip = QWidget(parent)
        strip.setObjectName("DashboardBalanceStrip")
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._balance_cards: dict[str, QLabel] = {}

        cards = [
            ("total_balance", "Total Cash & Bank", "DashboardBalanceCardBlue"),
            ("total_inflow", "Period Inflow", "DashboardBalanceCardGreen"),
            ("total_outflow", "Period Outflow", "DashboardBalanceCardAmber"),
        ]

        for key, title, obj_name in cards:
            card = QFrame(strip)
            card.setObjectName(obj_name)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(4)

            title_lbl = QLabel(title, card)
            title_lbl.setObjectName("DashboardBalanceCardTitle")
            card_layout.addWidget(title_lbl)

            value_lbl = QLabel("-", card)
            value_lbl.setObjectName("DashboardBalanceCardValue")
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            card_layout.addWidget(value_lbl)

            self._balance_cards[key] = value_lbl
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout.addWidget(card, 1)

        return strip

    def _reload_dashboard(self) -> None:
        active = self._active_company()
        if active is None:
            self._page_stack.setCurrentWidget(self._no_company_surface)
            return

        self._page_stack.setCurrentWidget(self._main_surface)

        try:
            self._data = self._service_registry.dashboard_service.get_dashboard_data(
                active.company_id, active.base_currency_code
            )
        except Exception:
            _log.exception("Dashboard data load failed")
            self._data = DashboardDataDTO()

        self._populate_context(self._data)
        self._populate_kpis(self._data.kpis, self._data.kpi_deltas)
        self._populate_setup_checklist(self._data.setup_checklist)
        self._populate_activity(self._data.recent_activity)
        self._populate_attention(self._data.attention_items)
        self._populate_aging(self._ar_aging_panel, self._data.ar_aging)
        self._populate_aging(self._ap_aging_panel, self._data.ap_aging)
        self._populate_cash_liquidity(self._data.cash_liquidity, self._data.kpis)
        self._record_telemetry(
            "dashboard",
            "loaded",
            setup_total=self._data.setup_checklist.total_count,
            setup_complete=self._data.setup_checklist.complete_count,
            attention_count=len(self._data.attention_items),
        )

    def _populate_context(self, data: DashboardDataDTO) -> None:
        as_of = data.as_of_date
        period = data.period_label
        if as_of:
            date_str = as_of.strftime("%d %b %Y")
            self._context_label.setText(
                f"As of {date_str}  |  {period}" if period else f"As of {date_str}"
            )
        else:
            self._context_label.setText("")

    def _populate_kpis(self, kpis: DashboardKpiDTO, deltas: DashboardKpiDeltaDTO | None = None) -> None:
        currency = kpis.currency_code

        def fmt(val: Decimal | None) -> str:
            if val is None:
                return "-"
            if abs(val) >= 1_000_000:
                return f"{currency} {val / 1_000_000:,.1f}M"
            if abs(val) >= 1_000:
                return f"{currency} {val / 1_000:,.1f}K"
            return f"{currency} {val:,.0f}"

        def fmt_with_delta(val: Decimal | None, delta_pct: Decimal | None) -> str:
            base = fmt(val)
            if delta_pct is None or val is None:
                return base
            # Round to integer percent for compactness
            pct_int = int(delta_pct.quantize(Decimal("1")))
            if pct_int == 0:
                return base
            arrow = "\u25B2" if pct_int > 0 else "\u25BC"
            return f"{base}  {arrow} {abs(pct_int)}%"

        rev_delta = deltas.revenue_delta_pct if deltas else None
        exp_delta = deltas.expenses_delta_pct if deltas else None

        items = [
            MoneyBarItem(
                label="Cash Position",
                value=fmt(kpis.cash_position),
                tone="info",
                nav_id_on_click=nav_ids.FINANCIAL_ACCOUNTS,
            ),
            MoneyBarItem(
                label="Receivables Due",
                value=fmt(kpis.receivables_due),
                tone="warning",
                nav_id_on_click=nav_ids.SALES_INVOICES,
            ),
            MoneyBarItem(
                label="Payables Due",
                value=fmt(kpis.payables_due),
                tone="warning",
                nav_id_on_click=nav_ids.PURCHASE_BILLS,
            ),
            MoneyBarItem(
                label="Period Revenue",
                value=fmt_with_delta(kpis.month_revenue, rev_delta),
                tone="success",
            ),
            MoneyBarItem(
                label="Period Expenses",
                value=fmt_with_delta(kpis.month_expenses, exp_delta),
                tone="neutral",
            ),
            MoneyBarItem(
                label="Pending Postings",
                value=str(kpis.pending_postings),
                tone="danger" if kpis.pending_postings > 0 else "neutral",
                nav_id_on_click=nav_ids.JOURNALS,
            ),
        ]
        self._money_bar.set_items(items)
        # Connect after set_items to avoid duplicate signal bindings on refresh
        try:
            self._money_bar.item_clicked.disconnect()
        except RuntimeError:
            pass
        self._money_bar.item_clicked.connect(self._navigate_to)

    def _populate_setup_checklist(self, checklist: DashboardSetupChecklistDTO) -> None:
        while self._setup_items_layout.count():
            child = self._setup_items_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not checklist.items:
            self._setup_checklist_panel.setVisible(False)
            return

        self._setup_checklist_panel.setVisible(True)
        self._setup_summary_label.setText(
            f"{checklist.complete_count} of {checklist.total_count} ready"
        )

        if checklist.is_complete:
            complete_state = build_empty_state("dashboard.setup_complete", parent=self._setup_items_container)
            complete_state.setMinimumHeight(90)
            complete_state.setMaximumHeight(130)
            self._setup_items_layout.addWidget(complete_state)
            return

        for item in checklist.items:
            row = QFrame(self._setup_items_container)
            row.setObjectName("DashboardSetupChecklistRow")
            row.setProperty("complete", item.is_complete)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(8)

            status = QLabel("Done" if item.is_complete else "Open", row)
            status.setObjectName("DashboardSetupStatus")
            status.setProperty("complete", item.is_complete)
            row_layout.addWidget(status)

            text_box = QWidget(row)
            text_layout = QVBoxLayout(text_box)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(1)
            label = QLabel(item.label, text_box)
            label.setObjectName("DashboardSetupLabel")
            detail = QLabel(item.detail, text_box)
            detail.setObjectName("DashboardSetupDetail")
            detail.setWordWrap(True)
            text_layout.addWidget(label)
            text_layout.addWidget(detail)
            row_layout.addWidget(text_box, 1)

            if not item.is_complete:
                button = QPushButton("Open", row)
                button.setObjectName("DashboardSetupOpenButton")
                describe_button(button, f"Open {item.label}", item.detail)
                button.clicked.connect(
                    lambda checked=False, nid=item.nav_id, key=item.key: self._open_setup_item(nid, key)
                )
                row_layout.addWidget(button)

            self._setup_items_layout.addWidget(row)

        self._record_telemetry(
            "setup_checklist",
            "displayed",
            complete_count=checklist.complete_count,
            total_count=checklist.total_count,
        )

    def _populate_activity(self, items: tuple[DashboardRecentActivityItemDTO, ...]) -> None:
        self._activity_model.removeRows(0, self._activity_model.rowCount())

        if not items:
            self._activity_table.setVisible(False)
            self._activity_empty.setVisible(True)
            return

        self._activity_table.setVisible(True)
        self._activity_empty.setVisible(False)

        for item in items:
            doc_type = _DOC_TYPE_LABELS.get(item.document_type, item.document_type.title())
            self._activity_model.appendRow([
                self._make_item(item.entry_date.strftime("%d %b %Y")),
                self._make_item(f"{doc_type} {item.document_number}", user_data=(item.nav_id, item.record_id)),
                self._make_item(item.description),
                self._make_item(f"{item.amount:,.2f}"),
                self._make_item(item.status_code.replace("_", " ").title()),
            ])

    def _populate_attention(self, items: tuple[DashboardAttentionItemDTO, ...]) -> None:
        while self._attention_layout.count():
            child = self._attention_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not items:
            self._attention_container.setVisible(False)
            self._attention_empty.setVisible(True)
            return

        self._attention_container.setVisible(True)
        self._attention_empty.setVisible(False)

        for item in items:
            row = QFrame(self._attention_container)
            row.setObjectName("DashboardAttentionRow")
            row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(10)

            dot = QLabel(row)
            dot.setObjectName("DashboardAttentionDot")
            dot.setProperty("severity", item.severity)
            dot.setFixedSize(QSize(8, 8))
            row_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

            label = QLabel(item.label, row)
            label.setObjectName("DashboardAttentionLabel")
            row_layout.addWidget(label, 1)

            count_badge = QLabel(str(item.count), row)
            count_badge.setObjectName("DashboardAttentionCount")
            count_badge.setProperty("severity", item.severity)
            row_layout.addWidget(count_badge)

            row.mousePressEvent = lambda _event, nid=item.nav_id: self._navigate_to(nid)
            self._attention_layout.addWidget(row)

    def _populate_aging(self, panel: QFrame, aging: DashboardAgingSnapshotDTO) -> None:
        bar: AgingBar = panel.property("_aging_bar")
        value_labels: list[QLabel] = panel.property("_aging_values")
        total_label: QLabel = panel.property("_aging_total")

        buckets = [
            aging.current, aging.bucket_1_30, aging.bucket_31_60,
            aging.bucket_61_90, aging.bucket_91_plus,
        ]
        bar.set_values(buckets)

        for lbl, val in zip(value_labels, buckets):
            lbl.setText(f"{val:,.0f}")

        total_label.setText(f"{aging.grand_total:,.0f}")

    def _populate_cash_liquidity(
        self, liquidity: DashboardCashLiquidityDTO, kpis: DashboardKpiDTO
    ) -> None:
        currency = kpis.currency_code

        def fmt(val: Decimal) -> str:
            if abs(val) >= 1_000_000:
                return f"{currency} {val / 1_000_000:,.2f}M"
            return f"{currency} {val:,.2f}"

        self._balance_cards["total_balance"].setText(fmt(liquidity.total_balance))
        self._balance_cards["total_inflow"].setText(fmt(liquidity.total_inflow))
        self._balance_cards["total_outflow"].setText(fmt(liquidity.total_outflow))

        # Populate trend chart
        if liquidity.trend_points:
            self._trend_chart.set_points(liquidity.trend_points)
            self._trend_chart.setVisible(True)
            self._trend_empty.setVisible(False)
        else:
            self._trend_chart.set_points(())
            self._trend_chart.setVisible(False)
            self._trend_empty.setVisible(True)

        self._accounts_model.removeRows(0, self._accounts_model.rowCount())

        if not liquidity.accounts:
            self._accounts_table.setVisible(False)
            self._accounts_empty.setVisible(True)
            return

        self._accounts_table.setVisible(True)
        self._accounts_empty.setVisible(False)

        for acct in liquidity.accounts:
            type_label = _ACCT_TYPE_LABELS.get(
                acct.account_type_code,
                acct.account_type_code.replace("_", " ").title(),
            )
            self._accounts_model.appendRow([
                self._make_item(f"{acct.account_code}  {acct.account_name}"),
                self._make_item(type_label),
                self._make_item(f"{acct.closing_balance:,.2f}"),
            ])

    def _on_activity_double_clicked(self, index) -> None:
        proxy = self._activity_table.view().model()
        src = proxy.mapToSource(index)
        row = src.row()
        doc_item = self._activity_model.item(row, 1)
        if doc_item is None:
            return
        data = doc_item.data(Qt.ItemDataRole.UserRole)
        if data and isinstance(data, tuple) and len(data) == 2:
            nav_id, _record_id = data
            self._navigate_to(nav_id)

    @staticmethod
    def _make_item(text, *, user_data=None) -> QStandardItem:
        item = QStandardItem("" if text is None else str(text))
        item.setEditable(False)
        if user_data is not None:
            item.setData(user_data, Qt.ItemDataRole.UserRole)
        return item

    def _navigate_to(self, nav_id: str) -> None:
        self._service_registry.navigation_service.navigate(nav_id)

    def _open_setup_item(self, nav_id: str, item_key: str) -> None:
        self._record_telemetry("setup_checklist", "open_item", item_key=item_key)
        self._navigate_to(nav_id)

    def _record_telemetry(self, funnel: str, step: str, **context: str | int | bool) -> None:
        self._telemetry.record_funnel_step(funnel=funnel, step=step, context=context)

    def _on_company_changed(self, *_args: Any) -> None:
        self._reload_dashboard()

    def _active_company(self) -> ActiveCompanyDTO | None:
        return self._service_registry.company_context_service.get_active_company()

    def set_navigation_context(self, context: dict[str, Any]) -> None:
        self._reload_dashboard()


# ======================================================================
# Aging bar widget
# ======================================================================

_AGING_COLORS_LIGHT = [
    LIGHT_PALETTE.accent,
    LIGHT_PALETTE.info,
    LIGHT_PALETTE.warning,
    LIGHT_PALETTE.status_warning_fg,
    LIGHT_PALETTE.danger,
]
_AGING_COLORS_DARK = [
    DARK_PALETTE.accent,
    DARK_PALETTE.info,
    DARK_PALETTE.warning,
    DARK_PALETTE.status_warning_fg,
    DARK_PALETTE.danger,
]


class AgingBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[Decimal] = [Decimal(0)] * 5
        self._total: Decimal = Decimal(0)
        self.setMinimumHeight(12)
        self.setMaximumHeight(16)

    def set_values(self, values: list[Decimal]) -> None:
        self._values = (
            values[:5] if len(values) >= 5 else values + [Decimal(0)] * (5 - len(values))
        )
        self._total = sum(self._values)
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = 4

        if self._total <= 0:
            painter.setPen(Qt.PenStyle.NoPen)
            is_dark = self.palette().window().color().lightness() < 128
            bg = QColor(DARK_PALETTE.secondary_surface if is_dark else LIGHT_PALETTE.secondary_surface)
            painter.setBrush(QBrush(bg))
            painter.drawRoundedRect(0, 0, w, h, radius, radius)
            painter.end()
            return

        is_dark = self.palette().window().color().lightness() < 128
        colors = _AGING_COLORS_DARK if is_dark else _AGING_COLORS_LIGHT

        raw_widths = [
            max(2.0, float(v / self._total) * w) if v > 0 else 0.0
            for v in self._values
        ]
        total_raw = sum(raw_widths)
        widths = [rw * w / total_raw for rw in raw_widths] if total_raw > 0 else raw_widths

        x = 0.0
        painter.setPen(Qt.PenStyle.NoPen)

        for idx, (seg_w, color_hex) in enumerate(zip(widths, colors)):
            if seg_w <= 0:
                continue
            painter.setBrush(QBrush(QColor(color_hex)))
            seg_x = round(x)
            seg_end = round(x + seg_w)
            actual_w = seg_end - seg_x

            if idx == 0 and actual_w == w:
                painter.drawRoundedRect(seg_x, 0, actual_w, h, radius, radius)
            elif idx == 0:
                painter.drawRoundedRect(seg_x, 0, actual_w + radius, h, radius, radius)
                painter.drawRect(seg_x + actual_w - 1, 0, radius + 1, h)
            elif x + seg_w >= w - 0.5:
                painter.drawRoundedRect(seg_x - radius, 0, actual_w + radius, h, radius, radius)
                painter.drawRect(seg_x, 0, radius, h)
            else:
                painter.drawRect(seg_x, 0, actual_w, h)

            x += seg_w

        painter.end()


# ======================================================================
# Cash inflow / outflow trend chart
# ======================================================================

_TREND_INFLOW_LIGHT = LIGHT_PALETTE.success
_TREND_OUTFLOW_LIGHT = LIGHT_PALETTE.warning
_TREND_INFLOW_DARK = DARK_PALETTE.success
_TREND_OUTFLOW_DARK = DARK_PALETTE.warning
_TREND_GRID_LIGHT = LIGHT_PALETTE.divider_subtle
_TREND_GRID_DARK = DARK_PALETTE.divider_subtle
_TREND_AXIS_LIGHT = LIGHT_PALETTE.text_secondary
_TREND_AXIS_DARK = DARK_PALETTE.text_secondary


class TrendChart(QWidget):
    """Simple dual-line chart plotting daily inflow (green) and outflow (amber)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._points: list[tuple[Any, Decimal, Decimal]] = []  # (date, inflow, outflow)
        self.setMinimumHeight(120)

    def set_points(self, points: Any) -> None:
        self._points = [(p.as_of, p.inflow, p.outflow) for p in points]
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        is_dark = self.palette().window().color().lightness() < 128
        inflow_color = QColor(_TREND_INFLOW_DARK if is_dark else _TREND_INFLOW_LIGHT)
        outflow_color = QColor(_TREND_OUTFLOW_DARK if is_dark else _TREND_OUTFLOW_LIGHT)
        grid_color = QColor(_TREND_GRID_DARK if is_dark else _TREND_GRID_LIGHT)
        axis_color = QColor(_TREND_AXIS_DARK if is_dark else _TREND_AXIS_LIGHT)

        padding_l = 8
        padding_r = 8
        padding_t = 8
        padding_b = 20  # room for x-axis labels

        plot_w = max(1, w - padding_l - padding_r)
        plot_h = max(1, h - padding_t - padding_b)

        # Baseline
        painter.setPen(grid_color)
        painter.drawLine(padding_l, padding_t + plot_h, padding_l + plot_w, padding_t + plot_h)

        if not self._points:
            painter.end()
            return

        max_val = Decimal("0")
        for _, inflow, outflow in self._points:
            if inflow > max_val:
                max_val = inflow
            if outflow > max_val:
                max_val = outflow
        if max_val <= 0:
            max_val = Decimal("1")

        n = len(self._points)
        if n == 1:
            step = 0
            x_positions = [padding_l + plot_w // 2]
        else:
            step = plot_w / (n - 1)
            x_positions = [int(padding_l + i * step) for i in range(n)]

        def _y(val: Decimal) -> int:
            if val <= 0:
                return padding_t + plot_h
            ratio = float(val) / float(max_val)
            ratio = max(0.0, min(1.0, ratio))
            return int(padding_t + plot_h - (ratio * plot_h))

        # Inflow polyline
        inflow_pen = painter.pen()
        painter.save()
        inflow_pen = painter.pen()
        inflow_pen.setColor(inflow_color)
        inflow_pen.setWidth(2)
        painter.setPen(inflow_pen)
        prev_x = None
        prev_y = None
        for x, (_, inflow, _outflow) in zip(x_positions, self._points):
            y = _y(inflow)
            if prev_x is not None:
                painter.drawLine(prev_x, prev_y, x, y)
            prev_x, prev_y = x, y
        painter.restore()

        # Outflow polyline
        painter.save()
        outflow_pen = painter.pen()
        outflow_pen.setColor(outflow_color)
        outflow_pen.setWidth(2)
        painter.setPen(outflow_pen)
        prev_x = None
        prev_y = None
        for x, (_, _inflow, outflow) in zip(x_positions, self._points):
            y = _y(outflow)
            if prev_x is not None:
                painter.drawLine(prev_x, prev_y, x, y)
            prev_x, prev_y = x, y
        painter.restore()

        # X-axis labels: first, middle, last
        painter.setPen(axis_color)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        label_indices = {0, n - 1}
        if n >= 3:
            label_indices.add(n // 2)

        for idx in sorted(label_indices):
            if idx < 0 or idx >= n:
                continue
            d = self._points[idx][0]
            label = d.strftime("%d %b")
            x = x_positions[idx]
            # Center the text around x
            text_w = painter.fontMetrics().horizontalAdvance(label)
            tx = max(0, min(w - text_w, x - text_w // 2))
            painter.drawText(tx, h - 4, label)

        painter.end()
