from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import (
    RatioAnalysisBundleDTO,
    RatioComponentDTO,
    RatioResultDTO,
    RatioTrendPointDTO,
)
from seeker_accounting.modules.reporting.services.financial_analysis_service import (
    BalanceAnalysisBasis,
    FinancialAnalysisSnapshot,
    MonthlyBalanceSnapshot,
    MonthlyProfitabilitySnapshot,
)
from seeker_accounting.modules.reporting.specs.financial_analysis_spec import (
    FORMULA_LABELS,
    MATERIAL_WORKING_CAPITAL_CHANGE_PERCENT,
    average_balance,
    evaluate_status,
    format_ratio_value,
    percent_change,
    period_day_count,
    ratio_change,
    safe_divide,
    to_amount,
    to_ratio,
)

_ZERO = Decimal("0.00")
_DAY_QUANTIZE = Decimal("0.1")


class RatioAnalysisService:
    """Builds 14H ratio DTOs from the shared financial-analysis snapshot."""

    def build_ratio_bundle(self, snapshot: FinancialAnalysisSnapshot) -> RatioAnalysisBundleDTO:
        ratios = (
            self._build_working_capital(snapshot),
            self._build_current_ratio(snapshot),
            self._build_quick_ratio(snapshot),
            self._build_cash_ratio(snapshot),
            self._build_dso(snapshot),
            self._build_dpo(snapshot),
            self._build_dio(snapshot),
            self._build_cash_conversion_cycle(snapshot),
            self._build_receivables_turnover(snapshot),
            self._build_payables_turnover(snapshot),
            self._build_inventory_turnover(snapshot),
            self._build_gross_margin(snapshot),
            self._build_operating_margin(snapshot),
            self._build_net_margin(snapshot),
            self._build_return_on_assets(snapshot),
            self._build_return_on_equity(snapshot),
            self._build_debt_to_equity(snapshot),
            self._build_debt_ratio(snapshot),
            self._build_equity_ratio(snapshot),
            self._build_liabilities_to_assets(snapshot),
        )
        warnings = tuple(ratio.unavailable_reason for ratio in ratios if ratio.unavailable_reason)
        return RatioAnalysisBundleDTO(
            ratios=ratios,
            by_code={ratio.ratio_code: ratio for ratio in ratios},
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _build_working_capital(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        current_value = self._working_capital_value(snapshot.current_balance_basis)
        prior_value = self._working_capital_value(snapshot.prior_balance_basis)
        change_amount = self._amount_change(current_value, prior_value)
        change_pct = percent_change(current_value, prior_value)
        if current_value is None:
            status_code, status_label = "unavailable", "Not available"
        elif current_value < _ZERO:
            status_code, status_label = "danger", "Negative"
        elif change_pct is not None and change_pct <= -MATERIAL_WORKING_CAPITAL_CHANGE_PERCENT:
            status_code, status_label = "warning", "Tightening"
        else:
            status_code, status_label = "success", "Positive cushion"
        return self._build_result(
            ratio_code="working_capital",
            label="Working Capital",
            category_code="liquidity",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            status_code=status_code,
            status_label=status_label,
            numerator_label="Current assets",
            denominator_label="Current liabilities",
            numerator_value=snapshot.current_balance_basis.current_assets,
            denominator_value=snapshot.current_balance_basis.current_liabilities,
            components=(
                self._balance_component(
                    label="Current assets",
                    amount=snapshot.current_balance_basis.current_assets,
                    line_code="TOTAL_CURRENT_ASSETS",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                self._balance_component(
                    label="Current liabilities",
                    amount=snapshot.current_balance_basis.current_liabilities,
                    line_code="TOTAL_CURRENT_LIABILITIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note="Balance-sheet snapshot uses posted IAS statement classifications at the selected statement date.",
            trend_points=self._balance_amount_trend(
                snapshot.monthly_balances,
                metric_code="working_capital",
            ),
            change_override=change_amount,
            change_percent_override=change_pct,
        )

    def _build_current_ratio(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        return self._build_balance_ratio(
            snapshot=snapshot,
            ratio_code="current_ratio",
            label="Current Ratio",
            numerator_label="Current assets",
            denominator_label="Current liabilities",
            numerator_current=snapshot.current_balance_basis.current_assets,
            denominator_current=snapshot.current_balance_basis.current_liabilities,
            numerator_prior=snapshot.prior_balance_basis.current_assets if snapshot.prior_balance_basis else None,
            denominator_prior=snapshot.prior_balance_basis.current_liabilities if snapshot.prior_balance_basis else None,
            components=(
                self._balance_component(
                    label="Current assets",
                    amount=snapshot.current_balance_basis.current_assets,
                    line_code="TOTAL_CURRENT_ASSETS",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                self._balance_component(
                    label="Current liabilities",
                    amount=snapshot.current_balance_basis.current_liabilities,
                    line_code="TOTAL_CURRENT_LIABILITIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            trend_points=self._balance_ratio_trend(
                snapshot.monthly_balances,
                "current_ratio",
                lambda item: safe_divide(item.current_assets, item.current_liabilities),
            ),
        )

    def _build_quick_ratio(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        current_quick_assets = (
            snapshot.current_balance_basis.current_assets - snapshot.current_balance_basis.inventories
        ).quantize(Decimal("0.01"))
        prior_quick_assets = None
        if snapshot.prior_balance_basis is not None:
            prior_quick_assets = (
                snapshot.prior_balance_basis.current_assets - snapshot.prior_balance_basis.inventories
            ).quantize(Decimal("0.01"))
        return self._build_balance_ratio(
            snapshot=snapshot,
            ratio_code="quick_ratio",
            label="Quick Ratio",
            numerator_label="Quick assets",
            denominator_label="Current liabilities",
            numerator_current=current_quick_assets,
            denominator_current=snapshot.current_balance_basis.current_liabilities,
            numerator_prior=prior_quick_assets,
            denominator_prior=snapshot.prior_balance_basis.current_liabilities if snapshot.prior_balance_basis else None,
            components=(
                RatioComponentDTO(
                    label="Current assets",
                    amount=snapshot.current_balance_basis.current_assets,
                    source_label="IAS/IFRS balance sheet",
                    detail_key=self._balance_detail_key(
                        "TOTAL_CURRENT_ASSETS",
                        snapshot.current_balance_basis.as_of_date,
                    ),
                ),
                RatioComponentDTO(
                    label="Less inventories",
                    amount=snapshot.current_balance_basis.inventories,
                    source_label="IAS/IFRS balance sheet",
                    detail_key=self._balance_detail_key(
                        "INVENTORIES",
                        snapshot.current_balance_basis.as_of_date,
                    ),
                ),
                self._balance_component(
                    label="Current liabilities",
                    amount=snapshot.current_balance_basis.current_liabilities,
                    line_code="TOTAL_CURRENT_LIABILITIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note="Quick assets exclude inventories to isolate liquid current-resource cover.",
            trend_points=self._balance_ratio_trend(
                snapshot.monthly_balances,
                "quick_ratio",
                lambda item: safe_divide(
                    (item.current_assets - item.inventories).quantize(Decimal("0.01")),
                    item.current_liabilities,
                ),
            ),
        )

    def _build_cash_ratio(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        return self._build_balance_ratio(
            snapshot=snapshot,
            ratio_code="cash_ratio",
            label="Cash Ratio",
            numerator_label="Cash and equivalents",
            denominator_label="Current liabilities",
            numerator_current=snapshot.current_balance_basis.cash_equivalents,
            denominator_current=snapshot.current_balance_basis.current_liabilities,
            numerator_prior=snapshot.prior_balance_basis.cash_equivalents if snapshot.prior_balance_basis else None,
            denominator_prior=snapshot.prior_balance_basis.current_liabilities if snapshot.prior_balance_basis else None,
            components=(
                self._balance_component(
                    label="Cash and cash equivalents",
                    amount=snapshot.current_balance_basis.cash_equivalents,
                    line_code="CASH_EQUIVALENTS",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                self._balance_component(
                    label="Current liabilities",
                    amount=snapshot.current_balance_basis.current_liabilities,
                    line_code="TOTAL_CURRENT_LIABILITIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note="Cash ratio is surfaced only from classified cash-equivalent balances and current liabilities.",
            trend_points=self._balance_ratio_trend(
                snapshot.monthly_balances,
                "cash_ratio",
                lambda item: safe_divide(item.cash_equivalents, item.current_liabilities),
            ),
        )

    def _build_dso(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        avg_receivables = average_balance(
            snapshot.current_balance_basis.receivables,
            snapshot.prior_balance_basis.receivables if snapshot.prior_balance_basis else None,
        )
        prior_avg_receivables = (
            average_balance(snapshot.prior_balance_basis.receivables, None)
            if snapshot.prior_balance_basis is not None
            else None
        )
        current_days = self._turnover_days(avg_receivables, snapshot.current_income_basis.revenue, snapshot)
        prior_days = (
            self._turnover_days(
                prior_avg_receivables,
                snapshot.prior_income_basis.revenue if snapshot.prior_income_basis else None,
                snapshot,
                use_prior_period=True,
            )
            if snapshot.prior_income_basis is not None
            else None
        )
        unavailable_reason = None
        if current_days is None:
            unavailable_reason = "DSO is unavailable because revenue was not positive enough to support a defensible collection-period calculation."
        return self._build_result(
            ratio_code="dso_days",
            label="Debtors Collection Period",
            category_code="efficiency",
            value=current_days,
            prior_value=prior_days,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="Average receivables",
            denominator_label="Revenue",
            numerator_value=avg_receivables,
            denominator_value=snapshot.current_income_basis.revenue,
            components=(
                self._balance_component(
                    label="Trade and other receivables",
                    amount=snapshot.current_balance_basis.receivables,
                    line_code="TRADE_OTHER_RECEIVABLES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                RatioComponentDTO(
                    label="Revenue",
                    amount=snapshot.current_income_basis.revenue,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="REV", ohada_code="XB"),
                ),
            ),
            basis_note=self._average_balance_note(snapshot),
            unavailable_reason=unavailable_reason,
        )

    def _build_dpo(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        avg_payables = average_balance(
            snapshot.current_balance_basis.payables,
            snapshot.prior_balance_basis.payables if snapshot.prior_balance_basis else None,
        )
        prior_avg_payables = (
            average_balance(snapshot.prior_balance_basis.payables, None)
            if snapshot.prior_balance_basis is not None
            else None
        )
        current_days = self._turnover_days(avg_payables, snapshot.purchase_total, snapshot)
        prior_days = (
            self._turnover_days(
                prior_avg_payables,
                snapshot.prior_purchase_total,
                snapshot,
                use_prior_period=True,
            )
            if snapshot.prior_purchase_total is not None
            else None
        )
        unavailable_reason = None
        if current_days is None:
            unavailable_reason = "DPO is unavailable because posted purchase-bill flow was insufficient for a reliable supplier-payment period."
        return self._build_result(
            ratio_code="dpo_days",
            label="Creditors Payment Period",
            category_code="efficiency",
            value=current_days,
            prior_value=prior_days,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="Average payables",
            denominator_label="Posted purchase bills",
            numerator_value=avg_payables,
            denominator_value=snapshot.purchase_total,
            components=(
                self._balance_component(
                    label="Trade and other payables",
                    amount=snapshot.current_balance_basis.payables,
                    line_code="CL_TRADE_OTHER_PAYABLES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                RatioComponentDTO(
                    label="Posted purchase bills",
                    amount=snapshot.purchase_total,
                    source_label="Posted purchase-bill truth",
                    detail_key=None,
                ),
            ),
            basis_note=(
                f"{self._average_balance_note(snapshot)} Posted purchase bills are used as the cleanest payable-flow basis already established in operational reporting."
            ),
            unavailable_reason=unavailable_reason,
        )

    def _build_dio(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        cost_of_sales = self._positive_expense_base(snapshot.current_income_basis.cost_of_sales)
        prior_cost_of_sales = (
            self._positive_expense_base(snapshot.prior_income_basis.cost_of_sales)
            if snapshot.prior_income_basis is not None
            else None
        )
        avg_inventory = average_balance(
            snapshot.current_balance_basis.inventories,
            snapshot.prior_balance_basis.inventories if snapshot.prior_balance_basis else None,
        )
        prior_avg_inventory = (
            average_balance(snapshot.prior_balance_basis.inventories, None)
            if snapshot.prior_balance_basis is not None
            else None
        )
        current_days = self._turnover_days(avg_inventory, cost_of_sales, snapshot)
        prior_days = (
            self._turnover_days(
                prior_avg_inventory,
                prior_cost_of_sales,
                snapshot,
                use_prior_period=True,
            )
            if snapshot.prior_income_basis is not None
            else None
        )
        unavailable_reason = None
        if current_days is None:
            unavailable_reason = (
                "Inventory holding period is unavailable because classified cost of sales was not safely supported by the current income-statement truth."
            )
        return self._build_result(
            ratio_code="dio_days",
            label="Inventory Holding Period",
            category_code="efficiency",
            value=current_days,
            prior_value=prior_days,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="Average inventory",
            denominator_label="Cost of sales",
            numerator_value=avg_inventory,
            denominator_value=cost_of_sales,
            components=(
                self._balance_component(
                    label="Inventories",
                    amount=snapshot.current_balance_basis.inventories,
                    line_code="INVENTORIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                RatioComponentDTO(
                    label="Cost of sales",
                    amount=cost_of_sales,
                    source_label="IAS income statement",
                    detail_key=self._income_detail_key(snapshot, ias_code="COS", ohada_code=None),
                ),
            ),
            basis_note=self._average_balance_note(snapshot),
            unavailable_reason=unavailable_reason,
        )

    def _build_cash_conversion_cycle(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        dso_ratio = self._build_dso(snapshot)
        dio_ratio = self._build_dio(snapshot)
        dpo_ratio = self._build_dpo(snapshot)
        value = None
        prior_value = None
        if dso_ratio.value is not None and dio_ratio.value is not None and dpo_ratio.value is not None:
            value = (dso_ratio.value + dio_ratio.value - dpo_ratio.value).quantize(
                _DAY_QUANTIZE,
                rounding=ROUND_HALF_UP,
            )
        if (
            dso_ratio.prior_value is not None
            and dio_ratio.prior_value is not None
            and dpo_ratio.prior_value is not None
        ):
            prior_value = (dso_ratio.prior_value + dio_ratio.prior_value - dpo_ratio.prior_value).quantize(
                _DAY_QUANTIZE,
                rounding=ROUND_HALF_UP,
            )
        unavailable_reason = None
        if value is None:
            unavailable_reason = "Cash conversion cycle is unavailable because one or more operating-cycle components could not be computed safely."
        return self._build_result(
            ratio_code="cash_conversion_cycle",
            label="Cash Conversion Cycle",
            category_code="efficiency",
            value=value,
            prior_value=prior_value,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="DSO + DIO",
            denominator_label="Less DPO",
            numerator_value=(
                (dso_ratio.value + dio_ratio.value).quantize(_DAY_QUANTIZE, rounding=ROUND_HALF_UP)
                if dso_ratio.value is not None and dio_ratio.value is not None
                else None
            ),
            denominator_value=dpo_ratio.value,
            components=(
                RatioComponentDTO(
                    label="DSO",
                    amount=dso_ratio.value,
                    source_label="Efficiency ratios",
                    detail_key="ratio|dso_days",
                ),
                RatioComponentDTO(
                    label="DIO",
                    amount=dio_ratio.value,
                    source_label="Efficiency ratios",
                    detail_key="ratio|dio_days",
                ),
                RatioComponentDTO(
                    label="Less DPO",
                    amount=dpo_ratio.value,
                    source_label="Efficiency ratios",
                    detail_key="ratio|dpo_days",
                ),
            ),
            basis_note="Cash conversion cycle is derived transparently from debtor days, inventory days, and creditor days already shown in this workspace.",
            unavailable_reason=unavailable_reason,
        )

    def _build_receivables_turnover(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        avg_receivables = average_balance(
            snapshot.current_balance_basis.receivables,
            snapshot.prior_balance_basis.receivables if snapshot.prior_balance_basis else None,
        )
        prior_avg_receivables = (
            average_balance(snapshot.prior_balance_basis.receivables, None)
            if snapshot.prior_balance_basis is not None
            else None
        )
        current_value = self._safe_positive_ratio(snapshot.current_income_basis.revenue, avg_receivables)
        prior_value = (
            self._safe_positive_ratio(
                snapshot.prior_income_basis.revenue if snapshot.prior_income_basis else None,
                prior_avg_receivables,
            )
            if snapshot.prior_income_basis is not None
            else None
        )
        unavailable_reason = None
        if current_value is None:
            unavailable_reason = "Receivables turnover is unavailable because revenue was not positive enough to support a defensible turnover measure."
        return self._build_result(
            ratio_code="receivables_turnover",
            label="Receivables Turnover",
            category_code="efficiency",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="Revenue",
            denominator_label="Average receivables",
            numerator_value=snapshot.current_income_basis.revenue,
            denominator_value=avg_receivables,
            components=(
                RatioComponentDTO(
                    label="Revenue",
                    amount=snapshot.current_income_basis.revenue,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="REV", ohada_code="XB"),
                ),
                self._balance_component(
                    label="Trade and other receivables",
                    amount=snapshot.current_balance_basis.receivables,
                    line_code="TRADE_OTHER_RECEIVABLES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note=self._average_balance_note(snapshot),
            unavailable_reason=unavailable_reason,
        )

    def _build_payables_turnover(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        avg_payables = average_balance(
            snapshot.current_balance_basis.payables,
            snapshot.prior_balance_basis.payables if snapshot.prior_balance_basis else None,
        )
        prior_avg_payables = (
            average_balance(snapshot.prior_balance_basis.payables, None)
            if snapshot.prior_balance_basis is not None
            else None
        )
        current_value = self._safe_positive_ratio(snapshot.purchase_total, avg_payables)
        prior_value = (
            self._safe_positive_ratio(snapshot.prior_purchase_total, prior_avg_payables)
            if snapshot.prior_purchase_total is not None
            else None
        )
        unavailable_reason = None
        if current_value is None:
            unavailable_reason = "Payables turnover is unavailable because posted purchase-bill flow was insufficient for a reliable turnover measure."
        return self._build_result(
            ratio_code="payables_turnover",
            label="Payables Turnover",
            category_code="efficiency",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="Posted purchase bills",
            denominator_label="Average payables",
            numerator_value=snapshot.purchase_total,
            denominator_value=avg_payables,
            components=(
                RatioComponentDTO(
                    label="Posted purchase bills",
                    amount=snapshot.purchase_total,
                    source_label="Posted purchase-bill truth",
                    detail_key=None,
                ),
                self._balance_component(
                    label="Trade and other payables",
                    amount=snapshot.current_balance_basis.payables,
                    line_code="CL_TRADE_OTHER_PAYABLES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note=(
                f"{self._average_balance_note(snapshot)} Purchase-bill throughput is used because supplier invoice truth is already established in operational reporting."
            ),
            unavailable_reason=unavailable_reason,
        )

    def _build_inventory_turnover(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        cost_of_sales = self._positive_expense_base(snapshot.current_income_basis.cost_of_sales)
        prior_cost_of_sales = (
            self._positive_expense_base(snapshot.prior_income_basis.cost_of_sales)
            if snapshot.prior_income_basis is not None
            else None
        )
        avg_inventory = average_balance(
            snapshot.current_balance_basis.inventories,
            snapshot.prior_balance_basis.inventories if snapshot.prior_balance_basis else None,
        )
        prior_avg_inventory = (
            average_balance(snapshot.prior_balance_basis.inventories, None)
            if snapshot.prior_balance_basis is not None
            else None
        )
        current_value = self._safe_positive_ratio(cost_of_sales, avg_inventory)
        prior_value = (
            self._safe_positive_ratio(prior_cost_of_sales, prior_avg_inventory)
            if snapshot.prior_income_basis is not None
            else None
        )
        unavailable_reason = None
        if current_value is None:
            unavailable_reason = "Inventory turnover is unavailable because classified cost of sales was not safely supported."
        return self._build_result(
            ratio_code="inventory_turnover",
            label="Inventory Turnover",
            category_code="efficiency",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="Cost of sales",
            denominator_label="Average inventory",
            numerator_value=cost_of_sales,
            denominator_value=avg_inventory,
            components=(
                RatioComponentDTO(
                    label="Cost of sales",
                    amount=cost_of_sales,
                    source_label="IAS income statement",
                    detail_key=self._income_detail_key(snapshot, ias_code="COS", ohada_code=None),
                ),
                self._balance_component(
                    label="Inventories",
                    amount=snapshot.current_balance_basis.inventories,
                    line_code="INVENTORIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note=self._average_balance_note(snapshot),
            unavailable_reason=unavailable_reason,
        )

    def _build_gross_margin(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        current_value = self._margin_value(
            snapshot.current_income_basis.gross_profit,
            snapshot.current_income_basis.revenue,
        )
        prior_value = (
            self._margin_value(
                snapshot.prior_income_basis.gross_profit,
                snapshot.prior_income_basis.revenue,
            )
            if snapshot.prior_income_basis is not None
            else None
        )
        unavailable_reason = None
        if current_value is None:
            unavailable_reason = "Gross margin is unavailable because classified gross-profit truth was not safely supported by the current reporting basis."
        return self._build_result(
            ratio_code="gross_margin",
            label="Gross Margin",
            category_code="profitability",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_filter.date_to,
            numerator_label="Gross profit",
            denominator_label="Revenue",
            numerator_value=snapshot.current_income_basis.gross_profit,
            denominator_value=snapshot.current_income_basis.revenue,
            components=(
                RatioComponentDTO(
                    label="Gross profit",
                    amount=snapshot.current_income_basis.gross_profit,
                    source_label="IAS income statement",
                    detail_key=self._income_detail_key(snapshot, ias_code="GROSS_PROFIT", ohada_code=None),
                ),
                RatioComponentDTO(
                    label="Revenue",
                    amount=snapshot.current_income_basis.revenue,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="REV", ohada_code="XB"),
                ),
            ),
            trend_points=self._profitability_ratio_trend(
                snapshot.monthly_profitability,
                "gross_margin",
                lambda item: None,
            ),
            unavailable_reason=unavailable_reason,
        )

    def _build_operating_margin(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        current_value = self._margin_value(
            snapshot.current_income_basis.operating_profit,
            snapshot.current_income_basis.revenue,
        )
        prior_value = (
            self._margin_value(
                snapshot.prior_income_basis.operating_profit,
                snapshot.prior_income_basis.revenue,
            )
            if snapshot.prior_income_basis is not None
            else None
        )
        return self._build_result(
            ratio_code="operating_margin",
            label="Operating Margin",
            category_code="profitability",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_filter.date_to,
            numerator_label="Operating profit",
            denominator_label="Revenue",
            numerator_value=snapshot.current_income_basis.operating_profit,
            denominator_value=snapshot.current_income_basis.revenue,
            components=(
                RatioComponentDTO(
                    label="Operating profit",
                    amount=snapshot.current_income_basis.operating_profit,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="OPERATING_PROFIT", ohada_code="XE"),
                ),
                RatioComponentDTO(
                    label="Revenue",
                    amount=snapshot.current_income_basis.revenue,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="REV", ohada_code="XB"),
                ),
            ),
            trend_points=self._profitability_ratio_trend(
                snapshot.monthly_profitability,
                "operating_margin",
                lambda item: safe_divide(item.profit, item.revenue) if item.revenue > _ZERO else None,
            ),
            unavailable_reason=(
                "Operating margin is unavailable because revenue or operating profit was not safely supported."
                if current_value is None
                else None
            ),
        )

    def _build_net_margin(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        current_value = self._margin_value(
            snapshot.current_income_basis.net_profit,
            snapshot.current_income_basis.revenue,
        )
        prior_value = (
            self._margin_value(
                snapshot.prior_income_basis.net_profit,
                snapshot.prior_income_basis.revenue,
            )
            if snapshot.prior_income_basis is not None
            else None
        )
        return self._build_result(
            ratio_code="net_margin",
            label="Net Margin",
            category_code="profitability",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_filter.date_to,
            numerator_label="Net profit",
            denominator_label="Revenue",
            numerator_value=snapshot.current_income_basis.net_profit,
            denominator_value=snapshot.current_income_basis.revenue,
            components=(
                RatioComponentDTO(
                    label="Net profit",
                    amount=snapshot.current_income_basis.net_profit,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="PROFIT_FOR_PERIOD", ohada_code="XI"),
                ),
                RatioComponentDTO(
                    label="Revenue",
                    amount=snapshot.current_income_basis.revenue,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="REV", ohada_code="XB"),
                ),
            ),
            trend_points=self._profitability_ratio_trend(
                snapshot.monthly_profitability,
                "net_margin",
                lambda item: safe_divide(item.profit, item.revenue) if item.revenue > _ZERO else None,
            ),
            unavailable_reason=(
                "Net margin is unavailable because revenue or net profit was not safely supported."
                if current_value is None
                else None
            ),
        )

    def _build_return_on_assets(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        avg_assets = average_balance(
            snapshot.current_balance_basis.total_assets,
            snapshot.prior_balance_basis.total_assets if snapshot.prior_balance_basis else None,
        )
        prior_avg_assets = (
            average_balance(snapshot.prior_balance_basis.total_assets, None)
            if snapshot.prior_balance_basis is not None
            else None
        )
        current_value = safe_divide(snapshot.current_income_basis.net_profit, avg_assets)
        prior_value = (
            safe_divide(
                snapshot.prior_income_basis.net_profit if snapshot.prior_income_basis else None,
                prior_avg_assets,
            )
            if snapshot.prior_income_basis is not None
            else None
        )
        return self._build_result(
            ratio_code="return_on_assets",
            label="Return on Assets",
            category_code="profitability",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="Net profit",
            denominator_label="Average total assets",
            numerator_value=snapshot.current_income_basis.net_profit,
            denominator_value=avg_assets,
            components=(
                RatioComponentDTO(
                    label="Net profit",
                    amount=snapshot.current_income_basis.net_profit,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="PROFIT_FOR_PERIOD", ohada_code="XI"),
                ),
                self._balance_component(
                    label="Total assets",
                    amount=snapshot.current_balance_basis.total_assets,
                    line_code="TOTAL_ASSETS",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note=self._average_balance_note(snapshot),
            trend_points=self._balance_profitability_trend(
                snapshot.monthly_balances,
                snapshot.monthly_profitability,
                "return_on_assets",
                lambda balance, profit: safe_divide(profit.profit, balance.total_assets),
            ),
            unavailable_reason=(
                "Return on assets is unavailable because average asset support or net profit was not safely supported."
                if current_value is None
                else None
            ),
        )

    def _build_return_on_equity(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        avg_equity = average_balance(
            snapshot.current_balance_basis.total_equity,
            snapshot.prior_balance_basis.total_equity if snapshot.prior_balance_basis else None,
        )
        prior_avg_equity = (
            average_balance(snapshot.prior_balance_basis.total_equity, None)
            if snapshot.prior_balance_basis is not None
            else None
        )
        current_value = None
        if avg_equity not in {None, _ZERO} and avg_equity > _ZERO:
            current_value = safe_divide(snapshot.current_income_basis.net_profit, avg_equity)
        prior_value = None
        if prior_avg_equity not in {None, _ZERO} and prior_avg_equity > _ZERO:
            prior_value = safe_divide(
                snapshot.prior_income_basis.net_profit if snapshot.prior_income_basis else None,
                prior_avg_equity,
            )
        unavailable_reason = None
        if current_value is None:
            unavailable_reason = "Return on equity is unavailable because equity was too thin or non-positive for a defensible average-equity return measure."
        return self._build_result(
            ratio_code="return_on_equity",
            label="Return on Equity",
            category_code="profitability",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label="Net profit",
            denominator_label="Average equity",
            numerator_value=snapshot.current_income_basis.net_profit,
            denominator_value=avg_equity,
            components=(
                RatioComponentDTO(
                    label="Net profit",
                    amount=snapshot.current_income_basis.net_profit,
                    source_label=self._income_source_label(snapshot.current_income_basis.basis_code),
                    detail_key=self._income_detail_key(snapshot, ias_code="PROFIT_FOR_PERIOD", ohada_code="XI"),
                ),
                self._balance_component(
                    label="Total equity",
                    amount=snapshot.current_balance_basis.total_equity,
                    line_code="TOTAL_EQUITY",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note=self._average_balance_note(snapshot),
            unavailable_reason=unavailable_reason,
        )

    def _build_debt_to_equity(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        return self._build_balance_ratio(
            snapshot=snapshot,
            ratio_code="debt_to_equity",
            label="Debt to Equity",
            numerator_label="Total liabilities",
            denominator_label="Total equity",
            numerator_current=snapshot.current_balance_basis.total_liabilities,
            denominator_current=snapshot.current_balance_basis.total_equity,
            numerator_prior=snapshot.prior_balance_basis.total_liabilities if snapshot.prior_balance_basis else None,
            denominator_prior=snapshot.prior_balance_basis.total_equity if snapshot.prior_balance_basis else None,
            components=(
                self._balance_component(
                    label="Current liabilities",
                    amount=snapshot.current_balance_basis.current_liabilities,
                    line_code="TOTAL_CURRENT_LIABILITIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                self._balance_component(
                    label="Non-current liabilities",
                    amount=snapshot.current_balance_basis.non_current_liabilities,
                    line_code="TOTAL_NON_CURRENT_LIABILITIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                self._balance_component(
                    label="Total equity",
                    amount=snapshot.current_balance_basis.total_equity,
                    line_code="TOTAL_EQUITY",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note="Debt-to-equity uses total liabilities against the equity buffer in the current balance-sheet truth.",
            trend_points=self._balance_ratio_trend(
                snapshot.monthly_balances,
                "debt_to_equity",
                lambda item: safe_divide(item.total_liabilities, item.total_equity),
            ),
        )

    def _build_debt_ratio(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        current_borrowings = (
            snapshot.current_balance_basis.current_borrowings + snapshot.current_balance_basis.non_current_borrowings
        ).quantize(Decimal("0.01"))
        prior_borrowings = None
        if snapshot.prior_balance_basis is not None:
            prior_borrowings = (
                snapshot.prior_balance_basis.current_borrowings + snapshot.prior_balance_basis.non_current_borrowings
            ).quantize(Decimal("0.01"))
        return self._build_balance_ratio(
            snapshot=snapshot,
            ratio_code="debt_ratio",
            label="Debt Ratio",
            numerator_label="Interest-bearing borrowings",
            denominator_label="Total assets",
            numerator_current=current_borrowings,
            denominator_current=snapshot.current_balance_basis.total_assets,
            numerator_prior=prior_borrowings,
            denominator_prior=snapshot.prior_balance_basis.total_assets if snapshot.prior_balance_basis else None,
            components=(
                RatioComponentDTO(
                    label="Current borrowings",
                    amount=snapshot.current_balance_basis.current_borrowings,
                    source_label="IAS/IFRS balance sheet",
                    detail_key=self._balance_detail_key(
                        "CL_BORROWINGS",
                        snapshot.current_balance_basis.as_of_date,
                    ),
                ),
                RatioComponentDTO(
                    label="Non-current borrowings",
                    amount=snapshot.current_balance_basis.non_current_borrowings,
                    source_label="IAS/IFRS balance sheet",
                    detail_key=self._balance_detail_key(
                        "NCL_BORROWINGS",
                        snapshot.current_balance_basis.as_of_date,
                    ),
                ),
                self._balance_component(
                    label="Total assets",
                    amount=snapshot.current_balance_basis.total_assets,
                    line_code="TOTAL_ASSETS",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            basis_note="Debt ratio is limited to interest-bearing borrowings rather than all liabilities.",
        )

    def _build_equity_ratio(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        return self._build_balance_ratio(
            snapshot=snapshot,
            ratio_code="equity_ratio",
            label="Equity Ratio",
            numerator_label="Total equity",
            denominator_label="Total assets",
            numerator_current=snapshot.current_balance_basis.total_equity,
            denominator_current=snapshot.current_balance_basis.total_assets,
            numerator_prior=snapshot.prior_balance_basis.total_equity if snapshot.prior_balance_basis else None,
            denominator_prior=snapshot.prior_balance_basis.total_assets if snapshot.prior_balance_basis else None,
            components=(
                self._balance_component(
                    label="Total equity",
                    amount=snapshot.current_balance_basis.total_equity,
                    line_code="TOTAL_EQUITY",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                self._balance_component(
                    label="Total assets",
                    amount=snapshot.current_balance_basis.total_assets,
                    line_code="TOTAL_ASSETS",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            trend_points=self._balance_ratio_trend(
                snapshot.monthly_balances,
                "equity_ratio",
                lambda item: safe_divide(item.total_equity, item.total_assets),
            ),
        )

    def _build_liabilities_to_assets(self, snapshot: FinancialAnalysisSnapshot) -> RatioResultDTO:
        return self._build_balance_ratio(
            snapshot=snapshot,
            ratio_code="liabilities_to_assets",
            label="Liabilities to Assets",
            numerator_label="Total liabilities",
            denominator_label="Total assets",
            numerator_current=snapshot.current_balance_basis.total_liabilities,
            denominator_current=snapshot.current_balance_basis.total_assets,
            numerator_prior=snapshot.prior_balance_basis.total_liabilities if snapshot.prior_balance_basis else None,
            denominator_prior=snapshot.prior_balance_basis.total_assets if snapshot.prior_balance_basis else None,
            components=(
                self._balance_component(
                    label="Current liabilities",
                    amount=snapshot.current_balance_basis.current_liabilities,
                    line_code="TOTAL_CURRENT_LIABILITIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                self._balance_component(
                    label="Non-current liabilities",
                    amount=snapshot.current_balance_basis.non_current_liabilities,
                    line_code="TOTAL_NON_CURRENT_LIABILITIES",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
                self._balance_component(
                    label="Total assets",
                    amount=snapshot.current_balance_basis.total_assets,
                    line_code="TOTAL_ASSETS",
                    as_of_date=snapshot.current_balance_basis.as_of_date,
                ),
            ),
            trend_points=self._balance_ratio_trend(
                snapshot.monthly_balances,
                "liabilities_to_assets",
                lambda item: safe_divide(item.total_liabilities, item.total_assets),
            ),
        )

    def _build_balance_ratio(
        self,
        *,
        snapshot: FinancialAnalysisSnapshot,
        ratio_code: str,
        label: str,
        numerator_label: str,
        denominator_label: str,
        numerator_current: Decimal | None,
        denominator_current: Decimal | None,
        numerator_prior: Decimal | None,
        denominator_prior: Decimal | None,
        components: tuple[RatioComponentDTO, ...],
        basis_note: str | None = None,
        trend_points: tuple[RatioTrendPointDTO, ...] = (),
    ) -> RatioResultDTO:
        current_value = safe_divide(numerator_current, denominator_current)
        prior_value = safe_divide(numerator_prior, denominator_prior)
        return self._build_result(
            ratio_code=ratio_code,
            label=label,
            category_code="liquidity" if ratio_code in {"current_ratio", "quick_ratio", "cash_ratio"} else "solvency",
            value=current_value,
            prior_value=prior_value,
            as_of_date=snapshot.current_balance_basis.as_of_date,
            numerator_label=numerator_label,
            denominator_label=denominator_label,
            numerator_value=numerator_current,
            denominator_value=denominator_current,
            components=components,
            basis_note=basis_note,
            trend_points=trend_points,
            unavailable_reason=(
                f"{label} is unavailable because the denominator was not safely supported."
                if current_value is None
                else None
            ),
        )

    def _build_result(
        self,
        *,
        ratio_code: str,
        label: str,
        category_code: str,
        value: Decimal | None,
        prior_value: Decimal | None,
        as_of_date: date | None,
        numerator_label: str | None = None,
        denominator_label: str | None = None,
        numerator_value: Decimal | None = None,
        denominator_value: Decimal | None = None,
        components: tuple[RatioComponentDTO, ...] = (),
        basis_note: str | None = None,
        trend_points: tuple[RatioTrendPointDTO, ...] = (),
        unavailable_reason: str | None = None,
        change_override: Decimal | None = None,
        change_percent_override: Decimal | None = None,
        status_code: str | None = None,
        status_label: str | None = None,
    ) -> RatioResultDTO:
        computed_change = change_override if change_override is not None else ratio_change(value, prior_value)
        computed_percent_change = (
            change_percent_override
            if change_percent_override is not None
            else percent_change(value, prior_value)
        )
        resolved_status_code, resolved_status_label = (
            (status_code, status_label)
            if status_code is not None and status_label is not None
            else evaluate_status(ratio_code, value)
        )
        return RatioResultDTO(
            ratio_code=ratio_code,
            label=label,
            category_code=category_code,
            formula_label=FORMULA_LABELS.get(ratio_code, label),
            display_value=format_ratio_value(ratio_code, value),
            value=value,
            status_code=resolved_status_code,
            status_label=resolved_status_label,
            as_of_date=as_of_date,
            numerator_label=numerator_label,
            denominator_label=denominator_label,
            numerator_value=numerator_value,
            denominator_value=denominator_value,
            prior_value=prior_value,
            prior_display_value=format_ratio_value(ratio_code, prior_value) if prior_value is not None else None,
            change_value=computed_change,
            change_percent=computed_percent_change,
            change_label=self._change_label(ratio_code, computed_change),
            basis_note=basis_note,
            unavailable_reason=unavailable_reason,
            detail_key=f"ratio|{ratio_code}",
            source_detail_keys=tuple(
                detail_key
                for detail_key in (component.detail_key for component in components)
                if detail_key
            ),
            components=components,
            trend_points=trend_points,
        )

    @staticmethod
    def _working_capital_value(balance: BalanceAnalysisBasis | None) -> Decimal | None:
        if balance is None:
            return None
        return (balance.current_assets - balance.current_liabilities).quantize(Decimal("0.01"))

    @staticmethod
    def _amount_change(current_value: Decimal | None, prior_value: Decimal | None) -> Decimal | None:
        if current_value is None or prior_value is None:
            return None
        return (current_value - prior_value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _turnover_days(
        numerator: Decimal | None,
        denominator: Decimal | None,
        snapshot: FinancialAnalysisSnapshot,
        *,
        use_prior_period: bool = False,
    ) -> Decimal | None:
        if denominator is None or denominator <= _ZERO or numerator is None:
            return None
        days = period_day_count(
            snapshot.prior_filter.date_from if use_prior_period and snapshot.prior_filter else snapshot.current_filter.date_from,
            snapshot.prior_filter.date_to if use_prior_period and snapshot.prior_filter else snapshot.current_filter.date_to,
        )
        if days is None:
            return None
        ratio = safe_divide(numerator, denominator)
        if ratio is None:
            return None
        return (ratio * days).quantize(_DAY_QUANTIZE, rounding=ROUND_HALF_UP)

    @staticmethod
    def _safe_positive_ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
        if numerator is None or numerator <= _ZERO or denominator is None or denominator <= _ZERO:
            return None
        return to_ratio(safe_divide(numerator, denominator))

    @staticmethod
    def _margin_value(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
        if numerator is None or denominator is None or denominator <= _ZERO:
            return None
        return to_ratio(safe_divide(numerator, denominator))

    @staticmethod
    def _positive_expense_base(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return abs(value).quantize(Decimal("0.01"))

    @staticmethod
    def _average_balance_note(snapshot: FinancialAnalysisSnapshot) -> str:
        if snapshot.prior_filter is None:
            return "Average-balance measures use the current statement balance because no comparable prior-period closing balance was available."
        return "Average-balance measures use current and prior statement balances to avoid overstating point-in-time efficiency."

    @staticmethod
    def _change_label(ratio_code: str, change_value: Decimal | None) -> str | None:
        if change_value is None:
            return None
        if ratio_code == "working_capital":
            return f"{change_value:,.2f}"
        if ratio_code in {"dso_days", "dpo_days", "dio_days", "cash_conversion_cycle"}:
            return f"{change_value:,.1f} days"
        if ratio_code in {
            "gross_margin",
            "operating_margin",
            "net_margin",
            "return_on_assets",
            "return_on_equity",
            "equity_ratio",
            "debt_ratio",
            "liabilities_to_assets",
        }:
            return f"{(change_value * Decimal('100')).quantize(Decimal('0.01')):,.2f} pts"
        return f"{change_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}x"

    @staticmethod
    def _balance_component(
        *,
        label: str,
        amount: Decimal | None,
        line_code: str,
        as_of_date: date | None,
    ) -> RatioComponentDTO:
        return RatioComponentDTO(
            label=label,
            amount=to_amount(amount),
            source_label="IAS/IFRS balance sheet",
            detail_key=RatioAnalysisService._balance_detail_key(line_code, as_of_date),
        )

    @staticmethod
    def _balance_detail_key(line_code: str, as_of_date: date | None) -> str | None:
        if as_of_date is None:
            return None
        return f"bs|{line_code}|{as_of_date.isoformat()}"

    @staticmethod
    def _period_detail_key(prefix: str, line_code: str, date_from: date | None, date_to: date | None) -> str | None:
        if date_from is None or date_to is None:
            return None
        return f"{prefix}|{line_code}|{date_from.isoformat()}|{date_to.isoformat()}"

    def _income_detail_key(
        self,
        snapshot: FinancialAnalysisSnapshot,
        *,
        ias_code: str,
        ohada_code: str | None,
    ) -> str | None:
        if snapshot.current_income_basis.basis_code == "ias":
            return self._period_detail_key(
                "is",
                ias_code,
                snapshot.current_filter.date_from,
                snapshot.current_filter.date_to,
            )
        if ohada_code is None:
            return None
        return self._period_detail_key(
            "ohada",
            ohada_code,
            snapshot.current_filter.date_from,
            snapshot.current_filter.date_to,
        )

    @staticmethod
    def _income_source_label(basis_code: str) -> str:
        return "IAS income statement" if basis_code == "ias" else "OHADA income statement"

    @staticmethod
    def _balance_ratio_trend(
        balances: tuple[MonthlyBalanceSnapshot, ...],
        metric_code: str,
        calculator,
    ) -> tuple[RatioTrendPointDTO, ...]:
        return tuple(
            RatioTrendPointDTO(
                label=item.label,
                value=to_ratio(calculator(item)),
                detail_key=f"ratio|{metric_code}",
            )
            for item in balances
        )

    @staticmethod
    def _balance_amount_trend(
        balances: tuple[MonthlyBalanceSnapshot, ...],
        *,
        metric_code: str,
    ) -> tuple[RatioTrendPointDTO, ...]:
        return tuple(
            RatioTrendPointDTO(
                label=item.label,
                value=(item.current_assets - item.current_liabilities).quantize(Decimal("0.01")),
                detail_key=f"ratio|{metric_code}",
            )
            for item in balances
        )

    @staticmethod
    def _profitability_ratio_trend(
        snapshots: tuple[MonthlyProfitabilitySnapshot, ...],
        metric_code: str,
        calculator,
    ) -> tuple[RatioTrendPointDTO, ...]:
        return tuple(
            RatioTrendPointDTO(
                label=item.label,
                value=to_ratio(calculator(item)),
                detail_key=f"ratio|{metric_code}",
            )
            for item in snapshots
        )

    @staticmethod
    def _balance_profitability_trend(
        balances: tuple[MonthlyBalanceSnapshot, ...],
        profits: tuple[MonthlyProfitabilitySnapshot, ...],
        metric_code: str,
        calculator,
    ) -> tuple[RatioTrendPointDTO, ...]:
        profit_map = {item.label: item for item in profits}
        points: list[RatioTrendPointDTO] = []
        for balance in balances:
            profit = profit_map.get(balance.label)
            points.append(
                RatioTrendPointDTO(
                    label=balance.label,
                    value=to_ratio(calculator(balance, profit)) if profit is not None else None,
                    detail_key=f"ratio|{metric_code}",
                )
            )
        return tuple(points)
