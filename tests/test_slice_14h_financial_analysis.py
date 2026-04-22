from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.ap_aging_report_dto import APAgingReportDTO
from seeker_accounting.modules.reporting.dto.ar_aging_report_dto import ARAgingReportDTO
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.services.financial_analysis_service import (
    BalanceAnalysisBasis,
    FinancialAnalysisSnapshot,
    IncomeAnalysisBasis,
    MonthlyBalanceSnapshot,
    MonthlyProfitabilitySnapshot,
)
from seeker_accounting.modules.reporting.services.financial_analysis_workspace_service import (
    FinancialAnalysisWorkspaceService,
)
from seeker_accounting.modules.reporting.services.insight_rules_service import InsightRulesService
from seeker_accounting.modules.reporting.services.interpretation_service import InterpretationService
from seeker_accounting.modules.reporting.services.ratio_analysis_service import RatioAnalysisService
from seeker_accounting.modules.reporting.services.reporting_workspace_service import (
    ReportingWorkspaceService,
)
from seeker_accounting.modules.reporting.services.working_capital_analysis_service import (
    WorkingCapitalAnalysisService,
)


class _FakeFinancialAnalysisService:
    def __init__(self, snapshot: FinancialAnalysisSnapshot) -> None:
        self._snapshot = snapshot

    def get_snapshot(self, filter_dto: ReportingFilterDTO) -> FinancialAnalysisSnapshot:  # noqa: ARG002
        return self._snapshot


def _sample_snapshot() -> FinancialAnalysisSnapshot:
    current_filter = ReportingFilterDTO(
        company_id=1,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 3, 31),
        posted_only=True,
    )
    prior_filter = ReportingFilterDTO(
        company_id=1,
        date_from=date(2025, 10, 1),
        date_to=date(2025, 12, 31),
        posted_only=True,
    )
    current_balance = BalanceAnalysisBasis(
        as_of_date=date(2026, 3, 31),
        total_assets=Decimal("500.00"),
        total_liabilities=Decimal("300.00"),
        total_equity=Decimal("200.00"),
        current_assets=Decimal("250.00"),
        current_liabilities=Decimal("150.00"),
        cash_equivalents=Decimal("60.00"),
        inventories=Decimal("80.00"),
        receivables=Decimal("90.00"),
        current_tax_assets=Decimal("10.00"),
        other_current_assets=Decimal("10.00"),
        payables=Decimal("70.00"),
        current_borrowings=Decimal("30.00"),
        non_current_borrowings=Decimal("90.00"),
        non_current_liabilities=Decimal("150.00"),
    )
    prior_balance = BalanceAnalysisBasis(
        as_of_date=date(2025, 12, 31),
        total_assets=Decimal("460.00"),
        total_liabilities=Decimal("260.00"),
        total_equity=Decimal("200.00"),
        current_assets=Decimal("230.00"),
        current_liabilities=Decimal("120.00"),
        cash_equivalents=Decimal("55.00"),
        inventories=Decimal("70.00"),
        receivables=Decimal("75.00"),
        current_tax_assets=Decimal("8.00"),
        other_current_assets=Decimal("22.00"),
        payables=Decimal("60.00"),
        current_borrowings=Decimal("25.00"),
        non_current_borrowings=Decimal("80.00"),
        non_current_liabilities=Decimal("140.00"),
    )
    current_income = IncomeAnalysisBasis(
        basis_code="ias",
        revenue=Decimal("400.00"),
        gross_profit=Decimal("160.00"),
        cost_of_sales=Decimal("-240.00"),
        operating_profit=Decimal("40.00"),
        operating_expenses=Decimal("-120.00"),
        net_profit=Decimal("28.00"),
        finance_income=Decimal("5.00"),
        finance_costs=Decimal("-7.00"),
        limitation_messages=(),
    )
    prior_income = IncomeAnalysisBasis(
        basis_code="ias",
        revenue=Decimal("380.00"),
        gross_profit=Decimal("150.00"),
        cost_of_sales=Decimal("-230.00"),
        operating_profit=Decimal("55.00"),
        operating_expenses=Decimal("-95.00"),
        net_profit=Decimal("36.00"),
        finance_income=Decimal("4.00"),
        finance_costs=Decimal("-6.00"),
        limitation_messages=(),
    )
    return FinancialAnalysisSnapshot(
        company_id=1,
        date_from=current_filter.date_from,
        date_to=current_filter.date_to,
        current_filter=current_filter,
        prior_filter=prior_filter,
        current_balance_sheet_report=object(),
        prior_balance_sheet_report=object(),
        current_ias_income_report=object(),
        prior_ias_income_report=object(),
        current_ohada_income_report=object(),
        prior_ohada_income_report=object(),
        current_ar_aging_report=ARAgingReportDTO(
            company_id=1,
            as_of_date=date(2026, 3, 31),
            total_bucket_31_60=Decimal("15.00"),
            total_bucket_61_90=Decimal("10.00"),
            total_bucket_91_plus=Decimal("5.00"),
        ),
        prior_ar_aging_report=ARAgingReportDTO(company_id=1, as_of_date=date(2025, 12, 31)),
        current_ap_aging_report=APAgingReportDTO(
            company_id=1,
            as_of_date=date(2026, 3, 31),
            total_bucket_31_60=Decimal("20.00"),
            total_bucket_61_90=Decimal("10.00"),
            total_bucket_91_plus=Decimal("5.00"),
        ),
        prior_ap_aging_report=APAgingReportDTO(company_id=1, as_of_date=date(2025, 12, 31)),
        current_stock_valuation_report=object(),
        current_balance_basis=current_balance,
        prior_balance_basis=prior_balance,
        current_income_basis=current_income,
        prior_income_basis=prior_income,
        sales_total=Decimal("400.00"),
        prior_sales_total=Decimal("380.00"),
        purchase_total=Decimal("200.00"),
        prior_purchase_total=Decimal("180.00"),
        monthly_profitability=(
            MonthlyProfitabilitySnapshot("Jan 2026", date(2026, 1, 1), date(2026, 1, 31), Decimal("120.00"), Decimal("98.00"), Decimal("22.00")),
            MonthlyProfitabilitySnapshot("Feb 2026", date(2026, 2, 1), date(2026, 2, 28), Decimal("130.00"), Decimal("101.00"), Decimal("29.00")),
            MonthlyProfitabilitySnapshot("Mar 2026", date(2026, 3, 1), date(2026, 3, 31), Decimal("150.00"), Decimal("123.00"), Decimal("27.00")),
        ),
        monthly_balances=(
            MonthlyBalanceSnapshot("Jan 2026", date(2026, 1, 31), Decimal("470.00"), Decimal("270.00"), Decimal("200.00"), Decimal("235.00"), Decimal("125.00"), Decimal("72.00"), Decimal("78.00"), Decimal("63.00"), Decimal("58.00")),
            MonthlyBalanceSnapshot("Feb 2026", date(2026, 2, 28), Decimal("485.00"), Decimal("286.00"), Decimal("199.00"), Decimal("244.00"), Decimal("138.00"), Decimal("75.00"), Decimal("84.00"), Decimal("68.00"), Decimal("57.00")),
            MonthlyBalanceSnapshot("Mar 2026", date(2026, 3, 31), Decimal("500.00"), Decimal("300.00"), Decimal("200.00"), Decimal("250.00"), Decimal("150.00"), Decimal("80.00"), Decimal("90.00"), Decimal("70.00"), Decimal("60.00")),
        ),
        monthly_sales_totals=(),
        monthly_purchase_totals=(),
        warnings=(),
        limitations=(),
    )


class RatioAnalysisServiceTests(unittest.TestCase):
    def test_builds_core_14h_ratios_from_grounded_snapshot(self) -> None:
        service = RatioAnalysisService()
        bundle = service.build_ratio_bundle(_sample_snapshot())

        self.assertEqual(bundle.by_code["current_ratio"].display_value, "1.67x")
        self.assertEqual(bundle.by_code["quick_ratio"].display_value, "1.13x")
        self.assertEqual(bundle.by_code["gross_margin"].display_value, "40.00%")
        self.assertEqual(bundle.by_code["cash_conversion_cycle"].display_value, "17.4 days")
        self.assertEqual(bundle.by_code["debt_to_equity"].display_value, "1.50x")
        self.assertEqual(bundle.by_code["working_capital"].display_value, "100.00")

    def test_marks_inventory_ratios_unavailable_when_cost_of_sales_truth_is_missing(self) -> None:
        snapshot = _sample_snapshot()
        snapshot = replace(
            snapshot,
            current_income_basis=replace(
                snapshot.current_income_basis,
                basis_code="ohada_fallback",
                gross_profit=None,
                cost_of_sales=None,
            ),
            prior_income_basis=replace(
                snapshot.prior_income_basis,
                basis_code="ohada_fallback",
                gross_profit=None,
                cost_of_sales=None,
            ),
        )
        bundle = RatioAnalysisService().build_ratio_bundle(snapshot)

        self.assertIsNone(bundle.by_code["dio_days"].value)
        self.assertIsNotNone(bundle.by_code["dio_days"].unavailable_reason)
        self.assertIsNone(bundle.by_code["inventory_turnover"].value)


class InsightRulesServiceTests(unittest.TestCase):
    def test_generates_specific_pressure_insights_from_deteriorating_signals(self) -> None:
        stressed = _sample_snapshot()
        stressed = replace(
            stressed,
            current_balance_basis=replace(
                stressed.current_balance_basis,
                current_assets=Decimal("120.00"),
                current_liabilities=Decimal("150.00"),
                inventories=Decimal("70.00"),
                receivables=Decimal("140.00"),
            ),
            current_income_basis=replace(
                stressed.current_income_basis,
                revenue=Decimal("300.00"),
                operating_profit=Decimal("9.00"),
                net_profit=Decimal("-4.00"),
            ),
        )
        bundle = RatioAnalysisService().build_ratio_bundle(stressed)
        insights = InsightRulesService().build_insights(stressed, bundle)
        insight_codes = {item.insight_code for item in insights}

        self.assertIn("liquidity_pressure", insight_codes)
        self.assertIn("collections_stretched", insight_codes)
        self.assertIn("margin_compression", insight_codes)


class FinancialAnalysisWorkspaceServiceTests(unittest.TestCase):
    def test_reporting_workspace_exposes_insights_launcher_tile(self) -> None:
        workspace = ReportingWorkspaceService().get_workspace_dto()
        insights_tab = next(tab for tab in workspace.tabs if tab.tab_key == "insights")

        self.assertTrue(insights_tab.is_launcher)
        self.assertEqual([tile.tile_key for tile in insights_tab.tiles], ["financial_analysis"])

    def test_workspace_assembles_overview_tabs_and_management_insights(self) -> None:
        snapshot = _sample_snapshot()
        workspace_service = FinancialAnalysisWorkspaceService(
            financial_analysis_service=_FakeFinancialAnalysisService(snapshot),
            ratio_analysis_service=RatioAnalysisService(),
            working_capital_analysis_service=WorkingCapitalAnalysisService(),
            insight_rules_service=InsightRulesService(),
            interpretation_service=InterpretationService(),
        )

        workspace = workspace_service.get_workspace(snapshot.current_filter)

        self.assertEqual(len(workspace.overview.headline_ratios), 8)
        self.assertTrue(workspace.liquidity.liquidity_ratios)
        self.assertTrue(workspace.efficiency.cycle_ratios)
        self.assertTrue(workspace.management_insights)


if __name__ == "__main__":
    unittest.main()
