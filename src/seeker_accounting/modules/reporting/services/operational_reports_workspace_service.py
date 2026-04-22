from __future__ import annotations

from seeker_accounting.modules.reporting.dto.reporting_workspace_dto import ReportTileDTO

_OPERATIONAL_REPORT_TILES: tuple[ReportTileDTO, ...] = (
    ReportTileDTO(
        tile_key="ar_aging",
        title="AR Aging",
        description=(
            "Customer-level receivables aging with posted-only document truth, "
            "bucket totals, and drilldown to supporting invoice and receipt activity."
        ),
        subtitle="Receivables",
    ),
    ReportTileDTO(
        tile_key="ap_aging",
        title="AP Aging",
        description=(
            "Supplier-level payables aging with posted bills, payments, "
            "bucket totals, and drilldown to the supporting source movements."
        ),
        subtitle="Payables",
    ),
    ReportTileDTO(
        tile_key="customer_statements",
        title="Customer Statements",
        description=(
            "Formal customer statement layouts with opening balance, period activity, "
            "closing balance, running balance, and print preview."
        ),
        subtitle="Subledger Statements",
    ),
    ReportTileDTO(
        tile_key="supplier_statements",
        title="Supplier Statements",
        description=(
            "Formal supplier statements built from posted AP truth, with "
            "opening, activity, closing, and source-document drilldown."
        ),
        subtitle="Subledger Statements",
    ),
    ReportTileDTO(
        tile_key="payroll_summary",
        title="Payroll Summaries",
        description=(
            "Operational payroll reporting across posted runs with gross pay, deductions, "
            "employer cost, net pay, settlement visibility, and employee summaries."
        ),
        subtitle="Payroll Operations",
    ),
    ReportTileDTO(
        tile_key="treasury_reports",
        title="Cash / Bank Reports",
        description=(
            "Cashbook and bankbook style operational views over posted treasury "
            "transactions and transfers with opening, movement, and closing balances."
        ),
        subtitle="Treasury",
    ),
)


class OperationalReportsWorkspaceService:
    """Provides launcher metadata for the Operational Reports workspace tab."""

    def list_tiles(self) -> tuple[ReportTileDTO, ...]:
        return _OPERATIONAL_REPORT_TILES
