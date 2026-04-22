from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.reporting.dto.insight_card_dto import (
    InsightCardDTO,
    InsightNumericBasisDTO,
)
from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioAnalysisBundleDTO, RatioResultDTO
from seeker_accounting.modules.reporting.services.financial_analysis_service import FinancialAnalysisSnapshot
from seeker_accounting.modules.reporting.specs.financial_analysis_spec import (
    MATERIAL_CYCLE_DAY_CHANGE,
    MATERIAL_LEVERAGE_CHANGE,
    MATERIAL_MARGIN_CHANGE_PERCENTAGE_POINTS,
    MATERIAL_WORKING_CAPITAL_CHANGE_PERCENT,
    format_ratio_value,
    percent_change,
    safe_divide,
    to_ratio,
)

_ZERO = Decimal("0.00")


class InsightRulesService:
    """Explainable rule engine for management insights grounded in report truth."""

    def build_insights(
        self,
        snapshot: FinancialAnalysisSnapshot,
        ratio_bundle: RatioAnalysisBundleDTO,
    ) -> tuple[InsightCardDTO, ...]:
        insights: list[InsightCardDTO] = []
        by_code = ratio_bundle.by_code

        current_ratio = by_code["current_ratio"]
        quick_ratio = by_code["quick_ratio"]
        working_capital = by_code["working_capital"]
        dso = by_code["dso_days"]
        dpo = by_code["dpo_days"]
        dio = by_code["dio_days"]
        ccc = by_code["cash_conversion_cycle"]
        operating_margin = by_code["operating_margin"]
        net_margin = by_code["net_margin"]
        debt_to_equity = by_code["debt_to_equity"]
        equity_ratio = by_code["equity_ratio"]

        inventory_share = to_ratio(
            safe_divide(
                snapshot.current_balance_basis.inventories,
                snapshot.current_balance_basis.current_assets,
            )
        )
        overdue_ap = (
            snapshot.current_ap_aging_report.total_bucket_31_60
            + snapshot.current_ap_aging_report.total_bucket_61_90
            + snapshot.current_ap_aging_report.total_bucket_91_plus
        ).quantize(Decimal("0.01"))
        overdue_ar = (
            snapshot.current_ar_aging_report.total_bucket_31_60
            + snapshot.current_ar_aging_report.total_bucket_61_90
            + snapshot.current_ar_aging_report.total_bucket_91_plus
        ).quantize(Decimal("0.01"))
        revenue_change_pct = percent_change(
            snapshot.current_income_basis.revenue,
            snapshot.prior_income_basis.revenue if snapshot.prior_income_basis else None,
        )
        operating_expense_change_pct = percent_change(
            self._positive(snapshot.current_income_basis.operating_expenses),
            self._positive(snapshot.prior_income_basis.operating_expenses) if snapshot.prior_income_basis else None,
        )

        if current_ratio.value is not None and quick_ratio.value is not None:
            if current_ratio.value < Decimal("1.00") and quick_ratio.value < Decimal("0.85"):
                insights.append(
                    self._card(
                        insight_code="liquidity_pressure",
                        title="Short-term liquidity cover is under pressure.",
                        statement=(
                            f"Current ratio fell to {current_ratio.display_value} and quick ratio sits at {quick_ratio.display_value}, "
                            "leaving limited headroom against short-term obligations."
                        ),
                        why_it_matters=(
                            "When quick cover trails current cover materially, the business has less flexibility to settle near-term liabilities without depending on stock conversion."
                        ),
                        severity_code="danger",
                        importance_rank=1,
                        numeric_basis=(
                            self._basis("Current ratio", current_ratio.display_value, "ratio|current_ratio"),
                            self._basis("Quick ratio", quick_ratio.display_value, "ratio|quick_ratio"),
                            self._basis("Working capital", working_capital.display_value, "ratio|working_capital"),
                        ),
                        comparison_text=self._comparison_text(current_ratio, quick_ratio),
                        detail_key="ratio|current_ratio",
                        related_ratio_codes=("current_ratio", "quick_ratio", "working_capital"),
                    )
                )

        if inventory_share is not None and inventory_share >= Decimal("0.45") and quick_ratio.value is not None:
            insights.append(
                self._card(
                    insight_code="inventory_heavy_liquidity",
                    title="Liquidity is becoming inventory-heavy.",
                    statement=(
                        f"Inventories represent {self._percent_text(inventory_share)} of current assets while quick ratio remains at {quick_ratio.display_value}."
                    ),
                    why_it_matters=(
                        "Strong current assets can mask weaker immediate liquidity if too much of the cover is tied up in inventory rather than cash or receivables."
                    ),
                    severity_code="warning" if quick_ratio.status_code != "danger" else "danger",
                    importance_rank=2,
                    numeric_basis=(
                        self._basis("Inventory share of current assets", self._percent_text(inventory_share), "bs|INVENTORIES|" + snapshot.current_balance_basis.as_of_date.isoformat() if snapshot.current_balance_basis.as_of_date else None),
                        self._basis("Quick ratio", quick_ratio.display_value, "ratio|quick_ratio"),
                    ),
                    comparison_text=None,
                    detail_key="ratio|quick_ratio",
                    related_ratio_codes=("quick_ratio", "current_ratio"),
                )
            )

        if dso.value is not None and dso.prior_value is not None:
            dso_increase = dso.value - dso.prior_value
            if dso_increase >= MATERIAL_CYCLE_DAY_CHANGE:
                severity = "danger" if revenue_change_pct is not None and revenue_change_pct < _ZERO else "warning"
                statement = (
                    f"DSO moved from {format_ratio_value('dso_days', dso.prior_value)} to {dso.display_value}"
                )
                if revenue_change_pct is not None:
                    statement += f" while revenue moved {revenue_change_pct:,.2f}%."
                insights.append(
                    self._card(
                        insight_code="collections_stretched",
                        title="Receivable collection has stretched materially.",
                        statement=statement,
                        why_it_matters=(
                            "Slower collections tie up cash in receivables and can intensify working-capital pressure when sales are not growing strongly enough to offset the delay."
                        ),
                        severity_code=severity,
                        importance_rank=3,
                        numeric_basis=(
                            self._basis("DSO", dso.display_value, "ratio|dso_days"),
                            self._basis("Overdue receivables", self._amount_text(overdue_ar), None),
                        ),
                        comparison_text=None,
                        detail_key="ratio|dso_days",
                        related_ratio_codes=("dso_days", "receivables_turnover"),
                    )
                )

        if ccc.value is not None and ccc.prior_value is not None:
            ccc_change = ccc.value - ccc.prior_value
            if ccc_change >= MATERIAL_CYCLE_DAY_CHANGE:
                insights.append(
                    self._card(
                        insight_code="cash_cycle_deterioration",
                        title="Cash conversion cycle has lengthened.",
                        statement=(
                            f"Cash conversion cycle moved from {format_ratio_value('cash_conversion_cycle', ccc.prior_value)} to {ccc.display_value}."
                        ),
                        why_it_matters=(
                            "A longer cash cycle means cash is tied up for more days across receivables and inventory before supplier credit offsets it."
                        ),
                        severity_code="warning",
                        importance_rank=4,
                        numeric_basis=(
                            self._basis("CCC", ccc.display_value, "ratio|cash_conversion_cycle"),
                            self._basis("DSO", dso.display_value, "ratio|dso_days"),
                            self._basis("DPO", dpo.display_value, "ratio|dpo_days"),
                            self._basis("DIO", dio.display_value, "ratio|dio_days"),
                        ),
                        comparison_text=None,
                        detail_key="ratio|cash_conversion_cycle",
                        related_ratio_codes=("cash_conversion_cycle", "dso_days", "dpo_days", "dio_days"),
                    )
                )

        if dpo.value is not None and dso.value is not None and dpo.value > dso.value and overdue_ap > _ZERO:
            insights.append(
                self._card(
                    insight_code="supplier_support_increasing",
                    title="Supplier support is helping the cash cycle.",
                    statement=(
                        f"DPO of {dpo.display_value} is now above DSO of {dso.display_value}, and overdue supplier balances total {self._amount_text(overdue_ap)}."
                    ),
                    why_it_matters=(
                        "Extended supplier credit can help liquidity temporarily, but rising reliance can become a fragility if overdue balances accumulate."
                    ),
                    severity_code="warning",
                    importance_rank=5,
                    numeric_basis=(
                        self._basis("DPO", dpo.display_value, "ratio|dpo_days"),
                        self._basis("DSO", dso.display_value, "ratio|dso_days"),
                        self._basis("Overdue AP", self._amount_text(overdue_ap), None),
                    ),
                    comparison_text=None,
                    detail_key="ratio|dpo_days",
                    related_ratio_codes=("dpo_days", "dso_days"),
                )
            )

        if operating_margin.value is not None and operating_margin.prior_value is not None:
            margin_drop = operating_margin.value - operating_margin.prior_value
            if margin_drop <= -Decimal("0.01") * MATERIAL_MARGIN_CHANGE_PERCENTAGE_POINTS:
                title = "Operating margin compressed faster than revenue."
                statement = (
                    f"Operating margin moved from {format_ratio_value('operating_margin', operating_margin.prior_value)} "
                    f"to {operating_margin.display_value}."
                )
                if revenue_change_pct is not None and operating_expense_change_pct is not None:
                    statement += (
                        f" Revenue changed {revenue_change_pct:,.2f}% while operating expenses changed {operating_expense_change_pct:,.2f}%."
                    )
                insights.append(
                    self._card(
                        insight_code="margin_compression",
                        title=title,
                        statement=statement,
                        why_it_matters=(
                            "When expenses rise faster than revenue, profitability deterioration is more likely to be operational than one-off."
                        ),
                        severity_code="danger" if net_margin.value is not None and net_margin.value < _ZERO else "warning",
                        importance_rank=6,
                        numeric_basis=(
                            self._basis("Operating margin", operating_margin.display_value, "ratio|operating_margin"),
                            self._basis("Net margin", net_margin.display_value, "ratio|net_margin"),
                        ),
                        comparison_text=None,
                        detail_key="ratio|operating_margin",
                        related_ratio_codes=("operating_margin", "net_margin"),
                    )
                )

        if net_margin.value is not None and net_margin.prior_value is not None and revenue_change_pct is not None:
            if net_margin.value > net_margin.prior_value and revenue_change_pct > _ZERO:
                insights.append(
                    self._card(
                        insight_code="profitability_improving",
                        title="Profitability is improving on real revenue growth.",
                        statement=(
                            f"Net margin improved to {net_margin.display_value} while revenue increased {revenue_change_pct:,.2f}%."
                        ),
                        why_it_matters=(
                            "Margin improvement supported by top-line growth is generally a healthier signal than one driven only by cost cuts or non-core items."
                        ),
                        severity_code="success",
                        importance_rank=7,
                        numeric_basis=(
                            self._basis("Net margin", net_margin.display_value, "ratio|net_margin"),
                            self._basis("Revenue movement", f"{revenue_change_pct:,.2f}%", "trend|revenue"),
                        ),
                        comparison_text=None,
                        detail_key="ratio|net_margin",
                        related_ratio_codes=("net_margin",),
                    )
                )

        if debt_to_equity.value is not None and debt_to_equity.prior_value is not None:
            leverage_change = debt_to_equity.value - debt_to_equity.prior_value
            if leverage_change >= MATERIAL_LEVERAGE_CHANGE:
                insights.append(
                    self._card(
                        insight_code="leverage_rising",
                        title="Leverage has stepped up materially.",
                        statement=(
                            f"Debt-to-equity moved from {format_ratio_value('debt_to_equity', debt_to_equity.prior_value)} "
                            f"to {debt_to_equity.display_value}."
                        ),
                        why_it_matters=(
                            "A faster rise in liabilities relative to equity reduces capital-structure flexibility and leaves a thinner buffer for shocks."
                        ),
                        severity_code="warning",
                        importance_rank=8,
                        numeric_basis=(
                            self._basis("Debt to equity", debt_to_equity.display_value, "ratio|debt_to_equity"),
                            self._basis("Equity ratio", equity_ratio.display_value, "ratio|equity_ratio"),
                        ),
                        comparison_text=None,
                        detail_key="ratio|debt_to_equity",
                        related_ratio_codes=("debt_to_equity", "equity_ratio"),
                    )
                )

        if equity_ratio.value is not None and equity_ratio.value < Decimal("0.25"):
            insights.append(
                self._card(
                    insight_code="equity_buffer_thin",
                    title="Equity buffer remains thin relative to liabilities.",
                    statement=(
                        f"Equity ratio is {equity_ratio.display_value} and debt-to-equity stands at {debt_to_equity.display_value}."
                    ),
                    why_it_matters=(
                        "Thin equity leaves less internal capital to absorb volatility, covenant pressure, or a temporary profit setback."
                    ),
                    severity_code="danger" if debt_to_equity.value is not None and debt_to_equity.value > Decimal("2.50") else "warning",
                    importance_rank=9,
                    numeric_basis=(
                        self._basis("Equity ratio", equity_ratio.display_value, "ratio|equity_ratio"),
                        self._basis("Debt to equity", debt_to_equity.display_value, "ratio|debt_to_equity"),
                    ),
                    comparison_text=None,
                    detail_key="ratio|equity_ratio",
                    related_ratio_codes=("equity_ratio", "debt_to_equity"),
                )
            )

        if working_capital.change_percent is not None and working_capital.change_percent <= -MATERIAL_WORKING_CAPITAL_CHANGE_PERCENT:
            insights.append(
                self._card(
                    insight_code="working_capital_weakened",
                    title="Working capital has weakened materially.",
                    statement=(
                        f"Working capital changed by {working_capital.change_percent:,.2f}% to {working_capital.display_value}."
                    ),
                    why_it_matters=(
                        "A shrinking working-capital cushion reduces room to absorb collection delays, stock build-up, or short-term funding stress."
                    ),
                    severity_code="warning" if working_capital.value is not None and working_capital.value > _ZERO else "danger",
                    importance_rank=10,
                    numeric_basis=(
                        self._basis("Working capital", working_capital.display_value, "ratio|working_capital"),
                        self._basis("Current ratio", current_ratio.display_value, "ratio|current_ratio"),
                    ),
                    comparison_text=None,
                    detail_key="ratio|working_capital",
                    related_ratio_codes=("working_capital", "current_ratio"),
                )
            )

        if not insights:
            insights.append(
                self._card(
                    insight_code="stable_financial_position",
                    title="Core financial signals remain relatively stable.",
                    statement=(
                        f"Current ratio is {current_ratio.display_value}, net margin is {net_margin.display_value}, and equity ratio is {equity_ratio.display_value}."
                    ),
                    why_it_matters=(
                        "When liquidity, profitability, and capital structure remain within a reasonable range, management can focus on selective operational improvements rather than immediate balance-sheet repair."
                    ),
                    severity_code="success",
                    importance_rank=99,
                    numeric_basis=(
                        self._basis("Current ratio", current_ratio.display_value, "ratio|current_ratio"),
                        self._basis("Net margin", net_margin.display_value, "ratio|net_margin"),
                        self._basis("Equity ratio", equity_ratio.display_value, "ratio|equity_ratio"),
                    ),
                    comparison_text=None,
                    detail_key="ratio|current_ratio",
                    related_ratio_codes=("current_ratio", "net_margin", "equity_ratio"),
                )
            )

        severity_order = {"danger": 0, "warning": 1, "info": 2, "success": 3}
        return tuple(
            sorted(
                insights,
                key=lambda item: (severity_order.get(item.severity_code, 9), item.importance_rank, item.title.lower()),
            )
        )

    @staticmethod
    def _card(
        *,
        insight_code: str,
        title: str,
        statement: str,
        why_it_matters: str,
        severity_code: str,
        importance_rank: int,
        numeric_basis: tuple[InsightNumericBasisDTO, ...],
        comparison_text: str | None,
        detail_key: str | None,
        related_ratio_codes: tuple[str, ...],
    ) -> InsightCardDTO:
        return InsightCardDTO(
            insight_code=insight_code,
            title=title,
            statement=statement,
            why_it_matters=why_it_matters,
            severity_code=severity_code,
            importance_rank=importance_rank,
            numeric_basis=numeric_basis,
            comparison_text=comparison_text,
            detail_key=f"insight|{insight_code}",
            related_ratio_codes=related_ratio_codes,
        )

    @staticmethod
    def _basis(label: str, value_text: str, detail_key: str | None) -> InsightNumericBasisDTO:
        return InsightNumericBasisDTO(label=label, value_text=value_text, detail_key=detail_key)

    @staticmethod
    def _comparison_text(*ratios: RatioResultDTO) -> str | None:
        parts = [
            f"{ratio.label}: {ratio.prior_display_value} -> {ratio.display_value}"
            for ratio in ratios
            if ratio.prior_display_value and ratio.display_value
        ]
        return " | ".join(parts) if parts else None

    @staticmethod
    def _percent_text(value: Decimal) -> str:
        return f"{(value * Decimal('100')).quantize(Decimal('0.01')):,.2f}%"

    @staticmethod
    def _amount_text(value: Decimal) -> str:
        return f"{value:,.2f}"

    @staticmethod
    def _positive(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return abs(value).quantize(Decimal("0.01"))
