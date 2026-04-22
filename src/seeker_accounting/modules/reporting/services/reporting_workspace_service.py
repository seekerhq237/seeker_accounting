from __future__ import annotations

import dataclasses

from seeker_accounting.app.security.permission_map import REPORT_TAB_PERMISSIONS, REPORT_TILE_PERMISSIONS
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.reporting.dto.reporting_workspace_dto import (
    ReportTabDTO,
    ReportTileDTO,
    ReportingWorkspaceDTO,
)
from seeker_accounting.modules.reporting.services.operational_reports_workspace_service import (
    OperationalReportsWorkspaceService,
)

_INCOME_STATEMENT_TILES: tuple[ReportTileDTO, ...] = (
    ReportTileDTO(
        tile_key="ohada_income_statement",
        title="OHADA Income Statement",
        description=(
            "Structured income statement following the OHADA SYSCOHADA framework. "
            "Presents operating revenue, operating charges, financial income and charges, "
            "and exceptional items in the OHADA-prescribed classification and layout."
        ),
        subtitle="SYSCOHADA Rev. 2017",
    ),
    ReportTileDTO(
        tile_key="ias_income_statement",
        title="IAS Income Statement Builder",
        description=(
            "Flexible income statement builder for IAS 1 compliance. "
            "Map chart-of-accounts groups to IFRS line items and produce "
            "a presentation-ready statement by nature or by function of expense."
        ),
        subtitle="IAS 1 / IFRS",
    ),
)

_BALANCE_SHEET_TILES: tuple[ReportTileDTO, ...] = (
    ReportTileDTO(
        tile_key="ohada_balance_sheet",
        title="OHADA Balance Sheet",
        description=(
            "Formal OHADA balance sheet using the locked SYSCOHADA structure with assets, "
            "depreciation/provisions, liabilities, equity, and drilldown to contributing accounts."
        ),
        subtitle="SYSCOHADA Rev. 2017",
    ),
    ReportTileDTO(
        tile_key="ias_balance_sheet",
        title="IAS/IFRS Balance Sheet",
        description=(
            "Locked statement of financial position aligned to IAS/IFRS presentation logic. "
            "Classifies posted balances into non-current and current assets, equity, and liabilities."
        ),
        subtitle="IAS / IFRS",
    ),
)

_ANALYTICS_TILES: tuple[ReportTileDTO, ...] = (
    ReportTileDTO(
        tile_key="financial_analysis",
        title="Financial Analysis & Insights",
        description=(
            "Executive financial analysis workspace covering ratios, working capital, operating cycle, "
            "trend movement, and rule-based management insights grounded in posted statement truth."
        ),
        subtitle="CFO Review Workspace",
    ),
)

_WORKSPACE_TABS: tuple[ReportTabDTO, ...] = (
    ReportTabDTO(
        tab_key="trial_balance",
        label="Trial Balance",
        description=(
            "Summarised debit and credit balances for all accounts in a selected period. "
            "Foundation check for period-end financial reporting."
        ),
    ),
    ReportTabDTO(
        tab_key="general_ledger",
        label="General Ledger",
        description=(
            "Detailed listing of posted journal entry lines per account. "
            "Full audit trail of accounting transactions with drilldown to source documents."
        ),
    ),
    ReportTabDTO(
        tab_key="income_statements",
        label="Income Statements",
        description="Income statement outputs for OHADA and IAS reporting frameworks.",
        is_launcher=True,
        tiles=_INCOME_STATEMENT_TILES,
    ),
    ReportTabDTO(
        tab_key="balance_sheet",
        label="Balance Sheet",
        description="Balance sheet outputs for OHADA and IAS/IFRS reporting frameworks.",
        is_launcher=True,
        tiles=_BALANCE_SHEET_TILES,
    ),
    ReportTabDTO(
        tab_key="operational_reports",
        label="Operational Reports",
        description=(
            "Operational reporting for receivables, payables, subledger statements, payroll, "
            "and cash or bank movement truth."
        ),
        is_launcher=True,
        tiles=OperationalReportsWorkspaceService().list_tiles(),
    ),
    ReportTabDTO(
        tab_key="analytics",
        label="Analytics",
        description="Financial analysis and comparative views derived from posted statement truth.",
        is_launcher=True,
        tiles=_ANALYTICS_TILES,
    ),
    ReportTabDTO(
        tab_key="insights",
        label="Insights",
        description="Rule-based management insights and executive financial review over reporting truth.",
        is_launcher=True,
        tiles=_ANALYTICS_TILES,
    ),
)


class ReportingWorkspaceService:
    """
    Assembles tab and tile metadata for the reports workspace,
    filtered to only the tabs and tiles the current user may access.
    Pure metadata assembly - no database access.
    """

    def __init__(self, permission_service: PermissionService | None = None) -> None:
        self._permission_service = permission_service

    def get_workspace_dto(self) -> ReportingWorkspaceDTO:
        if self._permission_service is None:
            return ReportingWorkspaceDTO(tabs=_WORKSPACE_TABS)

        visible_tabs: list[ReportTabDTO] = []
        for tab in _WORKSPACE_TABS:
            if not tab.is_launcher:
                required = REPORT_TAB_PERMISSIONS.get(tab.tab_key)
                if required and not self._permission_service.has_permission(required):
                    continue
                visible_tabs.append(tab)
            else:
                visible_tiles = tuple(
                    tile for tile in tab.tiles
                    if self._permission_service.has_permission(
                        REPORT_TILE_PERMISSIONS.get(tile.tile_key, "")
                    )
                )
                if not visible_tiles:
                    continue
                visible_tabs.append(dataclasses.replace(tab, tiles=visible_tiles))
        return ReportingWorkspaceDTO(tabs=tuple(visible_tabs))
