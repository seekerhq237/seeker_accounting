from __future__ import annotations

import dataclasses
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.reporting.dto.print_preview_dto import PrintPreviewMetaDTO
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.dto.reporting_workspace_dto import ReportTabDTO
from seeker_accounting.modules.reporting.dto.template_preview_dto import TemplatePreviewDTO
from seeker_accounting.modules.reporting.services.reporting_context_service import (
    ReportingContextService,
)
from seeker_accounting.modules.reporting.services.reporting_workspace_service import (
    ReportingWorkspaceService,
)
from seeker_accounting.modules.reporting.ui.dialogs.ap_aging_window import APAgingWindow
from seeker_accounting.modules.reporting.ui.dialogs.ar_aging_window import ARAgingWindow
from seeker_accounting.modules.reporting.ui.dialogs.customer_statement_window import (
    CustomerStatementWindow,
)
from seeker_accounting.modules.reporting.ui.dialogs.ias_balance_sheet_window import (
    IasBalanceSheetWindow,
)
from seeker_accounting.modules.reporting.ui.dialogs.financial_analysis_window import (
    FinancialAnalysisWindow,
)
from seeker_accounting.modules.reporting.ui.dialogs.ias_income_statement_builder_window import (
    IasIncomeStatementBuilderWindow,
)
from seeker_accounting.modules.reporting.ui.dialogs.ohada_balance_sheet_window import (
    OhadaBalanceSheetWindow,
)
from seeker_accounting.modules.reporting.ui.dialogs.ohada_income_statement_window import (
    OhadaIncomeStatementWindow,
)
from seeker_accounting.modules.reporting.ui.dialogs.report_print_preview_dialog import (
    ReportPrintPreviewDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.payroll_summary_window import (
    PayrollSummaryWindow,
)
from seeker_accounting.modules.reporting.ui.dialogs.report_template_preview_dialog import (
    ReportTemplatePreviewDialog,
)
from seeker_accounting.modules.reporting.ui.dialogs.supplier_statement_window import (
    SupplierStatementWindow,
)
from seeker_accounting.modules.reporting.ui.dialogs.treasury_report_window import (
    TreasuryReportWindow,
)
from seeker_accounting.modules.reporting.ui.widgets.report_tab_placeholder import (
    ReportTabPlaceholder,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_context_strip import (
    ReportingContextStrip,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_filter_bar import (
    ReportingFilterBar,
)
from seeker_accounting.modules.reporting.ui.widgets.reporting_tile_card import (
    ReportingTileCard,
)
from seeker_accounting.modules.reporting.ui.tabs.general_ledger_tab import GeneralLedgerTab
from seeker_accounting.modules.reporting.ui.tabs.trial_balance_tab import TrialBalanceTab


class _ReportLauncherTab(QWidget):
    """Inner widget for launcher tabs. Displays polished launch tiles."""

    def __init__(
        self,
        tab_dto: ReportTabDTO,
        service_registry: ServiceRegistry,
        filter_provider: Callable[[], ReportingFilterDTO] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._filter_provider = filter_provider

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel(tab_dto.label, self)
        title.setObjectName("ReportTabSectionTitle")
        outer.addWidget(title)

        outer.addSpacing(6)

        sub = QLabel(tab_dto.description, self)
        sub.setObjectName("ReportTabSubtitle")
        sub.setWordWrap(True)
        outer.addWidget(sub)

        outer.addSpacing(22)

        tiles_row = QWidget(self)
        tiles_layout = QHBoxLayout(tiles_row)
        tiles_layout.setContentsMargins(0, 0, 0, 0)
        tiles_layout.setSpacing(16)

        for tile_dto in tab_dto.tiles:
            card = ReportingTileCard(tile_dto, tiles_row)
            card.launched.connect(self._on_tile_launched)
            tiles_layout.addWidget(card, 1)

        outer.addWidget(tiles_row)
        outer.addStretch(1)

    def _on_tile_launched(self, tile_key: str) -> None:
        company_id = self._service_registry.active_company_context.company_id
        current_filter = self._filter_provider() if self._filter_provider is not None else None
        if tile_key == "ohada_income_statement":
            OhadaIncomeStatementWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "ias_income_statement":
            IasIncomeStatementBuilderWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "ohada_balance_sheet":
            OhadaBalanceSheetWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "ias_balance_sheet":
            IasBalanceSheetWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "ar_aging":
            ARAgingWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "ap_aging":
            APAgingWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "customer_statements":
            CustomerStatementWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "supplier_statements":
            SupplierStatementWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "payroll_summary":
            PayrollSummaryWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "treasury_reports":
            TreasuryReportWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )
        elif tile_key == "financial_analysis":
            FinancialAnalysisWindow.open(
                self._service_registry,
                company_id,
                initial_filter=current_filter,
                parent=self,
            )


class ReportsWorkspace(QWidget):
    """Main tabbed reports workspace."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ReportsWorkspace")

        self._service_registry = service_registry
        self._active_company_context = service_registry.active_company_context

        self._context_service = ReportingContextService(
            fiscal_calendar_service=service_registry.fiscal_calendar_service,
            active_company_context=service_registry.active_company_context,
        )
        self._workspace_service = ReportingWorkspaceService(
            permission_service=service_registry.permission_service,
        )
        self._trial_balance_tab: TrialBalanceTab | None = None
        self._general_ledger_tab: GeneralLedgerTab | None = None
        self._last_filter: ReportingFilterDTO | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._context_strip = ReportingContextStrip(self._context_service, service_registry, self)
        root.addWidget(self._context_strip)

        self._filter_bar = ReportingFilterBar(self)
        self._filter_bar.print_preview_requested.connect(self._on_print_preview)
        self._filter_bar.template_preview_requested.connect(self._on_template_preview)
        self._filter_bar.refresh_requested.connect(self._on_refresh_requested)
        root.addWidget(self._filter_bar)

        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("ReportsTabHost")
        root.addWidget(self._tabs, 1)

        workspace_dto = self._workspace_service.get_workspace_dto()
        for tab_dto in workspace_dto.tabs:
            if tab_dto.tab_key == "trial_balance":
                tab_widget = TrialBalanceTab(service_registry, self._tabs)
                tab_widget.drilldown_requested.connect(self._on_trial_balance_drilldown)
                self._trial_balance_tab = tab_widget
            elif tab_dto.tab_key == "general_ledger":
                tab_widget = GeneralLedgerTab(service_registry, self._tabs)
                self._general_ledger_tab = tab_widget
            elif tab_dto.is_launcher:
                tab_widget = _ReportLauncherTab(
                    tab_dto,
                    service_registry,
                    filter_provider=self._filter_bar.get_filter,
                    parent=self._tabs,
                )
            else:
                tab_widget = ReportTabPlaceholder(tab_dto, self._tabs)
            self._tabs.addTab(tab_widget, tab_dto.label)

        self._active_company_context.active_company_changed.connect(self._on_company_changed)
        self._sync_filter_bar_context()
        self._on_refresh_requested(self._filter_bar.get_filter())

    def _on_company_changed(self, company_id: object, company_name: object) -> None:  # noqa: ARG002
        self._sync_filter_bar_context()
        self._on_refresh_requested(self._filter_bar.get_filter())

    def _sync_filter_bar_context(self) -> None:
        company_id = self._active_company_context.company_id
        company_name = self._active_company_context.company_name or ""
        self._filter_bar.set_company_context(company_id, company_name)

    def _on_print_preview(self, meta: object) -> None:
        if not isinstance(meta, PrintPreviewMetaDTO):
            return
        current_tab_label = self._tabs.tabText(self._tabs.currentIndex())
        filter_summary = meta.filter_summary
        if self._general_ledger_tab is not None and self._tabs.currentWidget() is self._general_ledger_tab:
            account_label = self._general_ledger_tab.current_account_label()
            if account_label:
                filter_summary = f"{filter_summary} | Account: {account_label}"

        meta = dataclasses.replace(meta, report_title=current_tab_label, filter_summary=filter_summary)
        ReportPrintPreviewDialog.show_preview(meta, parent=self)

    def _on_template_preview(self, meta: object) -> None:
        if not isinstance(meta, TemplatePreviewDTO):
            return
        ReportTemplatePreviewDialog.show_template_preview(meta, parent=self)

    def _on_refresh_requested(self, filter_dto: object) -> None:
        if not isinstance(filter_dto, ReportingFilterDTO):
            return
        self._last_filter = filter_dto
        if self._trial_balance_tab is not None:
            self._trial_balance_tab.apply_filter(filter_dto)
        if self._general_ledger_tab is not None:
            self._general_ledger_tab.apply_filter(filter_dto)

    def _on_trial_balance_drilldown(self, account_id: int, account_code: str, account_name: str) -> None:
        if self._general_ledger_tab is None:
            return
        self._tabs.setCurrentWidget(self._general_ledger_tab)
        self._general_ledger_tab.focus_account(account_id, account_code, account_name)
        if self._last_filter is not None:
            self._general_ledger_tab.apply_filter(self._last_filter)
