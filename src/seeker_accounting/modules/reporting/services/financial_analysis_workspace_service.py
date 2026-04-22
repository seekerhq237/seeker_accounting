from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.financial_analysis_dto import (
    FinancialAnalysisOverviewDTO,
    FinancialAnalysisWorkspaceDTO,
)
from seeker_accounting.modules.reporting.dto.insight_card_dto import InsightCardDTO, InsightDetailDTO
from seeker_accounting.modules.reporting.dto.interpretation_dto import InterpretationPanelDTO
from seeker_accounting.modules.reporting.dto.print_preview_dto import PrintPreviewMetaDTO, PrintPreviewRowDTO
from seeker_accounting.modules.reporting.dto.profitability_analysis_dto import (
    ExpenseStructureRowDTO,
    ProfitabilityAnalysisDTO,
)
from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import (
    RatioAnalysisBundleDTO,
    RatioDetailDTO,
    RatioResultDTO,
)
from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.dto.solvency_analysis_dto import (
    CapitalStructureSliceDTO,
    SolvencyAnalysisDTO,
)
from seeker_accounting.modules.reporting.dto.trend_analysis_dto import (
    CompositionVarianceRowDTO,
    TrendAnalysisDTO,
    TrendDetailDTO,
    TrendPointDTO,
    TrendSeriesDTO,
    VarianceRowDTO,
)
from seeker_accounting.modules.reporting.services.financial_analysis_service import FinancialAnalysisService
from seeker_accounting.modules.reporting.services.insight_rules_service import InsightRulesService
from seeker_accounting.modules.reporting.services.interpretation_service import InterpretationService
from seeker_accounting.modules.reporting.services.ratio_analysis_service import RatioAnalysisService
from seeker_accounting.modules.reporting.services.working_capital_analysis_service import (
    WorkingCapitalAnalysisService,
)
from seeker_accounting.modules.reporting.specs.financial_analysis_spec import percent_change, safe_divide, to_ratio

try:
    from seeker_accounting.modules.administration.services.permission_service import PermissionService
except ImportError:
    PermissionService = None  # type: ignore[assignment,misc]

_ZERO = Decimal("0.00")


class FinancialAnalysisWorkspaceService:
    """Orchestrates the 14H workspace DTO from reporting truth and rule-based analysis."""

    def __init__(
        self,
        financial_analysis_service: FinancialAnalysisService,
        ratio_analysis_service: RatioAnalysisService,
        working_capital_analysis_service: WorkingCapitalAnalysisService,
        insight_rules_service: InsightRulesService,
        interpretation_service: InterpretationService,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._financial_analysis_service = financial_analysis_service
        self._ratio_analysis_service = ratio_analysis_service
        self._working_capital_analysis_service = working_capital_analysis_service
        self._insight_rules_service = insight_rules_service
        self._interpretation_service = interpretation_service
        self._permission_service = permission_service

    def get_workspace(self, filter_dto: ReportingFilterDTO) -> FinancialAnalysisWorkspaceDTO:
        if self._permission_service is not None:
            self._permission_service.require_permission("reports.financial_analysis.view")
        snapshot = self._financial_analysis_service.get_snapshot(filter_dto)
        ratio_bundle = self._ratio_analysis_service.build_ratio_bundle(snapshot)
        insights = self._insight_rules_service.build_insights(snapshot, ratio_bundle)

        liquidity_panel = self._panel(
            title="Liquidity readout",
            subtitle="Short-term solvency and working-capital cover.",
            insights=self._filter_insights(insights, {"working_capital", "current_ratio", "quick_ratio", "cash_ratio"}),
        )
        efficiency_panel = self._panel(
            title="Operating-cycle interpretation",
            subtitle="Receivables, inventory, payables, and cash-cycle signals.",
            insights=self._filter_insights(
                insights,
                {"dso_days", "dpo_days", "dio_days", "cash_conversion_cycle", "receivables_turnover", "payables_turnover"},
            ),
        )
        profitability_panel = self._panel(
            title="Profitability interpretation",
            subtitle="Margin direction, return quality, and cost pressure.",
            insights=self._filter_insights(insights, {"gross_margin", "operating_margin", "net_margin", "return_on_assets", "return_on_equity"}),
        )
        solvency_panel = self._panel(
            title="Capital-structure interpretation",
            subtitle="Leverage, equity buffer, and funding resilience.",
            insights=self._filter_insights(insights, {"debt_to_equity", "debt_ratio", "equity_ratio", "liabilities_to_assets"}),
        )
        trend_panel = self._panel(
            title="Trend interpretation",
            subtitle="What moved most across the selected comparison basis.",
            insights=self._filter_insights(
                insights,
                {"working_capital", "dso_days", "cash_conversion_cycle", "operating_margin", "net_margin", "debt_to_equity"},
            ),
        )

        working_capital_analysis = self._working_capital_analysis_service.build_working_capital_analysis(
            snapshot,
            ratio_bundle,
            interpretation_panel=liquidity_panel,
        )
        liquidity = self._working_capital_analysis_service.build_liquidity_analysis(
            snapshot,
            ratio_bundle,
            working_capital_analysis=working_capital_analysis,
            interpretation_panel=liquidity_panel,
        )
        efficiency = self._working_capital_analysis_service.build_efficiency_analysis(
            snapshot,
            ratio_bundle,
            interpretation_panel=efficiency_panel,
        )
        profitability = self._build_profitability(snapshot, ratio_bundle, profitability_panel)
        solvency = self._build_solvency(snapshot, ratio_bundle, solvency_panel)
        trend = self._build_trend(snapshot, ratio_bundle, trend_panel)
        overview = self._build_overview(ratio_bundle, insights)

        ratio_limitations = tuple(
            ratio.unavailable_reason
            for ratio in ratio_bundle.ratios
            if ratio.unavailable_reason
        )
        return FinancialAnalysisWorkspaceDTO(
            company_id=snapshot.company_id,
            date_from=snapshot.date_from,
            date_to=snapshot.date_to,
            period_label=self._period_label(snapshot.date_from, snapshot.date_to),
            overview=overview,
            liquidity=liquidity,
            efficiency=efficiency,
            profitability=profitability,
            solvency=solvency,
            trend=trend,
            management_insights=insights,
            warnings=snapshot.warnings,
            limitations=tuple(dict.fromkeys((*snapshot.limitations, *ratio_limitations))),
        )

    def _build_overview(
        self,
        ratio_bundle: RatioAnalysisBundleDTO,
        insights: tuple[InsightCardDTO, ...],
    ) -> FinancialAnalysisOverviewDTO:
        headline_codes = (
            "current_ratio",
            "quick_ratio",
            "gross_margin",
            "net_margin",
            "return_on_assets",
            "debt_to_equity",
            "working_capital",
            "cash_conversion_cycle",
        )
        warning_insights = tuple(card for card in insights if card.severity_code in {"danger", "warning"})[:4]
        strength_insights = tuple(card for card in insights if card.severity_code == "success")[:3]
        return FinancialAnalysisOverviewDTO(
            headline_ratios=tuple(ratio_bundle.by_code[code] for code in headline_codes),
            warning_insights=warning_insights,
            strength_insights=strength_insights,
        )

    def _build_profitability(
        self,
        snapshot,
        ratio_bundle: RatioAnalysisBundleDTO,
        interpretation_panel: InterpretationPanelDTO,
    ) -> ProfitabilityAnalysisDTO:
        revenue = snapshot.current_income_basis.revenue
        expense_rows = []
        for component_code, label, amount, detail_key in (
            ("cost_of_sales", "Cost of sales", self._positive(snapshot.current_income_basis.cost_of_sales), self._income_detail_key(snapshot, "COS", None)),
            ("operating_expenses", "Operating expenses", self._positive(snapshot.current_income_basis.operating_expenses), self._income_detail_key(snapshot, "OPERATING_EXPENSES", None if snapshot.current_income_basis.basis_code == "ias" else None)),
            ("finance_costs", "Finance costs", self._positive(snapshot.current_income_basis.finance_costs), None),
        ):
            if amount in {None, _ZERO}:
                continue
            expense_rows.append(
                ExpenseStructureRowDTO(
                    component_code=component_code,
                    label=label,
                    amount=amount,
                    share_of_revenue=to_ratio(safe_divide(amount, revenue)),
                    detail_key=detail_key,
                )
            )
        warnings = [
            ratio.unavailable_reason
            for ratio in (
                ratio_bundle.by_code["gross_margin"],
                ratio_bundle.by_code["operating_margin"],
                ratio_bundle.by_code["net_margin"],
                ratio_bundle.by_code["return_on_assets"],
                ratio_bundle.by_code["return_on_equity"],
            )
            if ratio.unavailable_reason
        ]
        return ProfitabilityAnalysisDTO(
            profitability_ratios=(
                ratio_bundle.by_code["gross_margin"],
                ratio_bundle.by_code["operating_margin"],
                ratio_bundle.by_code["net_margin"],
                ratio_bundle.by_code["return_on_assets"],
                ratio_bundle.by_code["return_on_equity"],
            ),
            expense_structure_rows=tuple(expense_rows),
            warnings=tuple(dict.fromkeys(warnings)),
            interpretation_panel=interpretation_panel,
        )

    def _build_solvency(
        self,
        snapshot,
        ratio_bundle: RatioAnalysisBundleDTO,
        interpretation_panel: InterpretationPanelDTO,
    ) -> SolvencyAnalysisDTO:
        total_assets = snapshot.current_balance_basis.total_assets
        current_borrowings = (
            snapshot.current_balance_basis.current_borrowings + snapshot.current_balance_basis.non_current_borrowings
        ).quantize(Decimal("0.01"))
        slices = (
            CapitalStructureSliceDTO(
                slice_code="equity",
                label="Equity",
                amount=snapshot.current_balance_basis.total_equity,
                share_percent=to_ratio(safe_divide(snapshot.current_balance_basis.total_equity, total_assets)),
                detail_key=self._balance_detail_key("TOTAL_EQUITY", snapshot.current_balance_basis.as_of_date),
            ),
            CapitalStructureSliceDTO(
                slice_code="current_liabilities",
                label="Current liabilities",
                amount=snapshot.current_balance_basis.current_liabilities,
                share_percent=to_ratio(safe_divide(snapshot.current_balance_basis.current_liabilities, total_assets)),
                detail_key=self._balance_detail_key("TOTAL_CURRENT_LIABILITIES", snapshot.current_balance_basis.as_of_date),
            ),
            CapitalStructureSliceDTO(
                slice_code="non_current_liabilities",
                label="Non-current liabilities",
                amount=snapshot.current_balance_basis.non_current_liabilities,
                share_percent=to_ratio(safe_divide(snapshot.current_balance_basis.non_current_liabilities, total_assets)),
                detail_key=self._balance_detail_key("TOTAL_NON_CURRENT_LIABILITIES", snapshot.current_balance_basis.as_of_date),
            ),
            CapitalStructureSliceDTO(
                slice_code="borrowings",
                label="Interest-bearing debt",
                amount=current_borrowings,
                share_percent=to_ratio(safe_divide(current_borrowings, total_assets)),
                detail_key=self._balance_detail_key("CL_BORROWINGS", snapshot.current_balance_basis.as_of_date),
            ),
        )
        warnings = [
            ratio.unavailable_reason
            for ratio in (
                ratio_bundle.by_code["debt_to_equity"],
                ratio_bundle.by_code["debt_ratio"],
                ratio_bundle.by_code["equity_ratio"],
                ratio_bundle.by_code["liabilities_to_assets"],
            )
            if ratio.unavailable_reason
        ]
        return SolvencyAnalysisDTO(
            solvency_ratios=(
                ratio_bundle.by_code["debt_to_equity"],
                ratio_bundle.by_code["debt_ratio"],
                ratio_bundle.by_code["equity_ratio"],
                ratio_bundle.by_code["liabilities_to_assets"],
            ),
            capital_structure_rows=tuple(slices),
            warnings=tuple(dict.fromkeys(warnings)),
            interpretation_panel=interpretation_panel,
        )

    def _build_trend(
        self,
        snapshot,
        ratio_bundle: RatioAnalysisBundleDTO,
        interpretation_panel: InterpretationPanelDTO,
    ) -> TrendAnalysisDTO:
        series = (
            TrendSeriesDTO(
                metric_code="revenue",
                label="Revenue",
                color_name="accent",
                points=tuple(TrendPointDTO(item.label, item.revenue, "trend|revenue") for item in snapshot.monthly_profitability),
            ),
            TrendSeriesDTO(
                metric_code="expenses",
                label="Expenses",
                color_name="warning",
                points=tuple(TrendPointDTO(item.label, item.expenses, "trend|expenses") for item in snapshot.monthly_profitability),
            ),
            TrendSeriesDTO(
                metric_code="profit",
                label="Profit",
                color_name="success",
                points=tuple(TrendPointDTO(item.label, item.profit, "trend|profit") for item in snapshot.monthly_profitability),
            ),
            TrendSeriesDTO(
                metric_code="assets",
                label="Assets",
                color_name="info",
                points=tuple(TrendPointDTO(item.label, item.total_assets, "trend|assets") for item in snapshot.monthly_balances),
            ),
            TrendSeriesDTO(
                metric_code="liabilities",
                label="Liabilities",
                color_name="danger",
                points=tuple(TrendPointDTO(item.label, item.total_liabilities, "trend|liabilities") for item in snapshot.monthly_balances),
            ),
            TrendSeriesDTO(
                metric_code="equity",
                label="Equity",
                color_name="success",
                points=tuple(TrendPointDTO(item.label, item.total_equity, "trend|equity") for item in snapshot.monthly_balances),
            ),
            TrendSeriesDTO(
                metric_code="working_capital",
                label="Working Capital",
                color_name="warning",
                points=tuple(
                    TrendPointDTO(
                        item.label,
                        (item.current_assets - item.current_liabilities).quantize(Decimal("0.01")),
                        "trend|working_capital",
                    )
                    for item in snapshot.monthly_balances
                ),
            ),
        )
        variance_rows = (
            self._variance_row("revenue", "Revenue", snapshot.current_income_basis.revenue, snapshot.prior_income_basis.revenue if snapshot.prior_income_basis else None, "trend|revenue"),
            self._variance_row("operating_expenses", "Operating expenses", self._positive(snapshot.current_income_basis.operating_expenses), self._positive(snapshot.prior_income_basis.operating_expenses) if snapshot.prior_income_basis else None, "trend|expenses", lower_is_better=True),
            self._variance_row("profit", "Net profit", snapshot.current_income_basis.net_profit, snapshot.prior_income_basis.net_profit if snapshot.prior_income_basis else None, "trend|profit"),
            self._variance_row("assets", "Total assets", snapshot.current_balance_basis.total_assets, snapshot.prior_balance_basis.total_assets if snapshot.prior_balance_basis else None, "trend|assets"),
            self._variance_row("liabilities", "Total liabilities", snapshot.current_balance_basis.total_liabilities, snapshot.prior_balance_basis.total_liabilities if snapshot.prior_balance_basis else None, "trend|liabilities", lower_is_better=True),
            self._variance_row("equity", "Total equity", snapshot.current_balance_basis.total_equity, snapshot.prior_balance_basis.total_equity if snapshot.prior_balance_basis else None, "trend|equity"),
            self._variance_row("working_capital", "Working capital", ratio_bundle.by_code["working_capital"].value, ratio_bundle.by_code["working_capital"].prior_value, "trend|working_capital"),
        )
        borrowings = (
            snapshot.current_balance_basis.current_borrowings + snapshot.current_balance_basis.non_current_borrowings
        ).quantize(Decimal("0.01"))
        prior_borrowings = None
        if snapshot.prior_balance_basis is not None:
            prior_borrowings = (
                snapshot.prior_balance_basis.current_borrowings + snapshot.prior_balance_basis.non_current_borrowings
            ).quantize(Decimal("0.01"))
        composition_rows = (
            self._composition_variance("cash", "Cash and equivalents", snapshot.current_balance_basis.cash_equivalents, snapshot.prior_balance_basis.cash_equivalents if snapshot.prior_balance_basis else None, self._balance_detail_key("CASH_EQUIVALENTS", snapshot.current_balance_basis.as_of_date)),
            self._composition_variance("receivables", "Receivables", snapshot.current_balance_basis.receivables, snapshot.prior_balance_basis.receivables if snapshot.prior_balance_basis else None, self._balance_detail_key("TRADE_OTHER_RECEIVABLES", snapshot.current_balance_basis.as_of_date)),
            self._composition_variance("inventories", "Inventories", snapshot.current_balance_basis.inventories, snapshot.prior_balance_basis.inventories if snapshot.prior_balance_basis else None, self._balance_detail_key("INVENTORIES", snapshot.current_balance_basis.as_of_date)),
            self._composition_variance("payables", "Payables", snapshot.current_balance_basis.payables, snapshot.prior_balance_basis.payables if snapshot.prior_balance_basis else None, self._balance_detail_key("CL_TRADE_OTHER_PAYABLES", snapshot.current_balance_basis.as_of_date)),
            self._composition_variance("borrowings", "Interest-bearing borrowings", borrowings, prior_borrowings, self._balance_detail_key("CL_BORROWINGS", snapshot.current_balance_basis.as_of_date)),
        )
        warnings = tuple(dict.fromkeys(snapshot.limitations))
        return TrendAnalysisDTO(
            series=series,
            variance_rows=variance_rows,
            composition_rows=composition_rows,
            warnings=warnings,
            interpretation_panel=interpretation_panel,
        )

    def build_ratio_detail(self, workspace: FinancialAnalysisWorkspaceDTO, ratio_code: str) -> RatioDetailDTO:
        ratio = self._ratio_map(workspace)[ratio_code]
        comparison = None
        if ratio.prior_display_value is not None:
            comparison = f"Prior period: {ratio.prior_display_value}"
            if ratio.change_label:
                comparison += f" | Change: {ratio.change_label}"
        return RatioDetailDTO(
            ratio_code=ratio.ratio_code,
            title=ratio.label,
            subtitle=f"Period: {workspace.period_label}",
            formula_label=ratio.formula_label,
            value_text=ratio.display_value,
            status_label=ratio.status_label,
            basis_note=ratio.basis_note,
            comparison_text=comparison,
            unavailable_reason=ratio.unavailable_reason,
            components=ratio.components,
        )

    def build_insight_detail(self, workspace: FinancialAnalysisWorkspaceDTO, insight_code: str) -> InsightDetailDTO:
        card = next(item for item in workspace.management_insights if item.insight_code == insight_code)
        ratio_map = self._ratio_map(workspace)
        related_ratios = tuple(ratio_map[code] for code in card.related_ratio_codes if code in ratio_map)
        return InsightDetailDTO(
            period_label=workspace.period_label,
            card=card,
            related_ratios=related_ratios,
            limitations=workspace.limitations,
        )

    def build_trend_detail(self, workspace: FinancialAnalysisWorkspaceDTO, metric_code: str) -> TrendDetailDTO:
        series = tuple(item for item in workspace.trend.series if item.metric_code == metric_code)
        if not series:
            series = workspace.trend.series
        variance_rows = tuple(row for row in workspace.trend.variance_rows if row.metric_code == metric_code) or workspace.trend.variance_rows
        title = next((item.label for item in workspace.trend.series if item.metric_code == metric_code), "Trend Detail")
        return TrendDetailDTO(
            metric_code=metric_code,
            title=title,
            subtitle=f"Period: {workspace.period_label}",
            series=series,
            variance_rows=variance_rows,
        )

    def build_print_preview_meta(
        self,
        workspace: FinancialAnalysisWorkspaceDTO,
        section_key: str,
        company_name: str,
    ) -> PrintPreviewMetaDTO:
        if section_key == "insights":
            rows = tuple(
                PrintPreviewRowDTO(
                    row_type="line",
                    reference_code=card.severity_code.upper(),
                    label=card.title,
                    amount_text=" | ".join(f"{item.label}: {item.value_text}" for item in card.numeric_basis[:2]),
                    secondary_amount_text=card.comparison_text or "",
                )
                for card in workspace.management_insights
            )
            title = "Financial Analysis | Insight Summary"
        elif section_key == "ratios":
            rows = self._ratio_rows(self._ratio_map(workspace).values())
            title = "Financial Analysis | Ratio Summary"
        else:
            rows = self._ratio_rows(workspace.overview.headline_ratios)
            title = "Financial Analysis | Overview Summary"
        return PrintPreviewMetaDTO(
            report_title=title,
            company_name=company_name,
            period_label=workspace.period_label,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            filter_summary=f"Warnings: {len(workspace.warnings)} | Limitations: {len(workspace.limitations)}",
            amount_headers=("Current", "Prior", "Change"),
            rows=rows,
        )

    def _panel(
        self,
        *,
        title: str,
        subtitle: str,
        insights: tuple[InsightCardDTO, ...],
    ) -> InterpretationPanelDTO:
        return self._interpretation_service.build_panel(
            title=title,
            subtitle=subtitle,
            insights=insights,
        )

    @staticmethod
    def _period_label(date_from, date_to) -> str:
        if date_from and date_to:
            return f"{date_from.strftime('%Y-%m-%d')} to {date_to.strftime('%Y-%m-%d')}"
        if date_to:
            return f"As at {date_to.strftime('%Y-%m-%d')}"
        if date_from:
            return f"From {date_from.strftime('%Y-%m-%d')}"
        return "Current selection"

    @staticmethod
    def _filter_insights(insights: tuple[InsightCardDTO, ...], ratio_codes: set[str]) -> tuple[InsightCardDTO, ...]:
        return tuple(
            card
            for card in insights
            if ratio_codes.intersection(card.related_ratio_codes)
        )[:3]

    @staticmethod
    def _ratio_map(workspace: FinancialAnalysisWorkspaceDTO) -> dict[str, RatioResultDTO]:
        ratios = [
            *workspace.overview.headline_ratios,
            *workspace.liquidity.liquidity_ratios,
            *workspace.efficiency.cycle_ratios,
            *workspace.profitability.profitability_ratios,
            *workspace.solvency.solvency_ratios,
            workspace.liquidity.working_capital_analysis.net_working_capital,
        ]
        return {ratio.ratio_code: ratio for ratio in ratios}

    @staticmethod
    def _variance_row(metric_code: str, label: str, current_value, prior_value, detail_key: str, *, lower_is_better: bool = False) -> VarianceRowDTO:
        variance_value = None if current_value is None or prior_value is None else (current_value - prior_value).quantize(Decimal("0.01"))
        variance_percent = percent_change(current_value, prior_value)
        status_code = "neutral"
        if variance_value is not None:
            if variance_value > _ZERO:
                status_code = "warning" if lower_is_better else "success"
            elif variance_value < _ZERO:
                status_code = "success" if lower_is_better else "warning"
        return VarianceRowDTO(
            metric_code=metric_code,
            label=label,
            current_value=current_value,
            prior_value=prior_value,
            variance_value=variance_value,
            variance_percent=variance_percent,
            status_code=status_code,
            detail_key=detail_key,
        )

    @staticmethod
    def _composition_variance(component_code: str, label: str, current_value, prior_value, detail_key: str | None) -> CompositionVarianceRowDTO:
        variance_value = None if current_value is None or prior_value is None else (current_value - prior_value).quantize(Decimal("0.01"))
        return CompositionVarianceRowDTO(
            component_code=component_code,
            label=label,
            current_value=current_value,
            prior_value=prior_value,
            variance_value=variance_value,
            detail_key=detail_key,
        )

    @staticmethod
    def _ratio_rows(ratios) -> tuple[PrintPreviewRowDTO, ...]:
        return tuple(
            PrintPreviewRowDTO(
                row_type="line",
                reference_code=ratio.label,
                label=ratio.formula_label,
                amount_text=ratio.display_value,
                secondary_amount_text=ratio.prior_display_value or "",
                tertiary_amount_text=ratio.change_label or "",
            )
            for ratio in ratios
        )

    @staticmethod
    def _balance_detail_key(line_code: str, as_of_date) -> str | None:
        if as_of_date is None:
            return None
        return f"bs|{line_code}|{as_of_date.isoformat()}"

    @staticmethod
    def _income_detail_key(snapshot, ias_code: str, ohada_code: str | None) -> str | None:
        if snapshot.current_filter.date_from is None or snapshot.current_filter.date_to is None:
            return None
        if snapshot.current_income_basis.basis_code == "ias":
            return f"is|{ias_code}|{snapshot.current_filter.date_from.isoformat()}|{snapshot.current_filter.date_to.isoformat()}"
        if ohada_code is None:
            return None
        return f"ohada|{ohada_code}|{snapshot.current_filter.date_from.isoformat()}|{snapshot.current_filter.date_to.isoformat()}"

    @staticmethod
    def _positive(value):
        if value is None:
            return None
        return abs(value).quantize(Decimal("0.01"))
