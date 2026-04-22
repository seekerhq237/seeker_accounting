from __future__ import annotations

from decimal import Decimal

from seeker_accounting.modules.reporting.dto.efficiency_analysis_dto import EfficiencyAnalysisDTO
from seeker_accounting.modules.reporting.dto.interpretation_dto import InterpretationPanelDTO
from seeker_accounting.modules.reporting.dto.liquidity_analysis_dto import LiquidityAnalysisDTO
from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioAnalysisBundleDTO
from seeker_accounting.modules.reporting.dto.working_capital_dto import (
    WorkingCapitalAnalysisDTO,
    WorkingCapitalCompositionRowDTO,
)
from seeker_accounting.modules.reporting.services.financial_analysis_service import FinancialAnalysisSnapshot
from seeker_accounting.modules.reporting.specs.financial_analysis_spec import safe_divide, to_ratio

_ZERO = Decimal("0.00")


class WorkingCapitalAnalysisService:
    """Builds liquidity, working-capital, and operating-cycle views from ratio truth."""

    def build_working_capital_analysis(
        self,
        snapshot: FinancialAnalysisSnapshot,
        ratio_bundle: RatioAnalysisBundleDTO,
        interpretation_panel: InterpretationPanelDTO | None = None,
    ) -> WorkingCapitalAnalysisDTO:
        current_assets = snapshot.current_balance_basis.current_assets
        current_liabilities = snapshot.current_balance_basis.current_liabilities
        warnings: list[str] = []

        current_asset_rows = (
            self._composition_row(
                component_code="cash",
                label="Cash and cash equivalents",
                amount=snapshot.current_balance_basis.cash_equivalents,
                total=current_assets,
                detail_key=self._balance_detail_key("CASH_EQUIVALENTS", snapshot.current_balance_basis.as_of_date),
            ),
            self._composition_row(
                component_code="receivables",
                label="Trade and other receivables",
                amount=snapshot.current_balance_basis.receivables,
                total=current_assets,
                detail_key=self._balance_detail_key(
                    "TRADE_OTHER_RECEIVABLES",
                    snapshot.current_balance_basis.as_of_date,
                ),
            ),
            self._composition_row(
                component_code="inventories",
                label="Inventories",
                amount=snapshot.current_balance_basis.inventories,
                total=current_assets,
                detail_key=self._balance_detail_key("INVENTORIES", snapshot.current_balance_basis.as_of_date),
            ),
            self._composition_row(
                component_code="tax_assets",
                label="Current tax assets",
                amount=snapshot.current_balance_basis.current_tax_assets,
                total=current_assets,
                detail_key=self._balance_detail_key(
                    "CURRENT_TAX_ASSETS",
                    snapshot.current_balance_basis.as_of_date,
                ),
            ),
            self._composition_row(
                component_code="other_current_assets",
                label="Other current assets",
                amount=snapshot.current_balance_basis.other_current_assets,
                total=current_assets,
                detail_key=self._balance_detail_key(
                    "OTHER_CURRENT_ASSETS",
                    snapshot.current_balance_basis.as_of_date,
                ),
            ),
        )

        residual_current_liabilities = (
            current_liabilities
            - snapshot.current_balance_basis.payables
            - snapshot.current_balance_basis.current_borrowings
        ).quantize(Decimal("0.01"))
        if residual_current_liabilities < _ZERO:
            warnings.append(
                "Current-liability composition contains overlapping mapped balances, so residual short-term obligations were clipped to zero for presentation."
            )
            residual_current_liabilities = _ZERO

        current_liability_rows = (
            self._composition_row(
                component_code="payables",
                label="Trade and other payables",
                amount=snapshot.current_balance_basis.payables,
                total=current_liabilities,
                detail_key=self._balance_detail_key(
                    "CL_TRADE_OTHER_PAYABLES",
                    snapshot.current_balance_basis.as_of_date,
                ),
            ),
            self._composition_row(
                component_code="current_borrowings",
                label="Current borrowings",
                amount=snapshot.current_balance_basis.current_borrowings,
                total=current_liabilities,
                detail_key=self._balance_detail_key(
                    "CL_BORROWINGS",
                    snapshot.current_balance_basis.as_of_date,
                ),
            ),
            self._composition_row(
                component_code="other_current_liabilities",
                label="Other current liabilities",
                amount=residual_current_liabilities,
                total=current_liabilities,
                detail_key=self._balance_detail_key(
                    "TOTAL_CURRENT_LIABILITIES",
                    snapshot.current_balance_basis.as_of_date,
                ),
            ),
        )

        net_working_capital = ratio_bundle.by_code["working_capital"]
        current_ratio = ratio_bundle.by_code["current_ratio"]
        quick_ratio = ratio_bundle.by_code["quick_ratio"]
        inventory_share = to_ratio(safe_divide(snapshot.current_balance_basis.inventories, current_assets))

        if net_working_capital.value is not None and net_working_capital.value < _ZERO:
            warnings.append("Working capital is negative at the selected statement date.")
        if current_ratio.status_code == "danger":
            warnings.append("Current liabilities exceed the current-resource cover implied by the classified balance sheet.")
        if (
            inventory_share is not None
            and inventory_share >= Decimal("0.45")
            and quick_ratio.status_code in {"warning", "danger"}
        ):
            warnings.append("Liquidity coverage is materially dependent on inventories rather than immediately liquid resources.")

        return WorkingCapitalAnalysisDTO(
            net_working_capital=net_working_capital,
            current_asset_rows=tuple(row for row in current_asset_rows if row.amount != _ZERO),
            current_liability_rows=tuple(row for row in current_liability_rows if row.amount != _ZERO),
            warnings=tuple(dict.fromkeys(warnings)),
            interpretation_panel=interpretation_panel,
        )

    def build_liquidity_analysis(
        self,
        snapshot: FinancialAnalysisSnapshot,
        ratio_bundle: RatioAnalysisBundleDTO,
        *,
        working_capital_analysis: WorkingCapitalAnalysisDTO,
        interpretation_panel: InterpretationPanelDTO | None = None,
    ) -> LiquidityAnalysisDTO:
        warnings = list(working_capital_analysis.warnings)
        for ratio_code in ("current_ratio", "quick_ratio", "cash_ratio"):
            ratio = ratio_bundle.by_code[ratio_code]
            if ratio.unavailable_reason:
                warnings.append(ratio.unavailable_reason)
            elif ratio.status_code in {"warning", "danger"}:
                warnings.append(f"{ratio.label}: {ratio.status_label}.")
        if snapshot.current_ap_aging_report.total_bucket_61_90 + snapshot.current_ap_aging_report.total_bucket_91_plus > _ZERO:
            warnings.append("A portion of supplier balances is already materially overdue, which can tighten short-term solvency flexibility.")
        return LiquidityAnalysisDTO(
            working_capital_analysis=working_capital_analysis,
            liquidity_ratios=(
                ratio_bundle.by_code["current_ratio"],
                ratio_bundle.by_code["quick_ratio"],
                ratio_bundle.by_code["cash_ratio"],
            ),
            warnings=tuple(dict.fromkeys(warnings)),
            interpretation_panel=interpretation_panel,
        )

    def build_efficiency_analysis(
        self,
        snapshot: FinancialAnalysisSnapshot,
        ratio_bundle: RatioAnalysisBundleDTO,
        interpretation_panel: InterpretationPanelDTO | None = None,
    ) -> EfficiencyAnalysisDTO:
        warnings: list[str] = []
        for ratio_code in (
            "dso_days",
            "dpo_days",
            "dio_days",
            "cash_conversion_cycle",
            "receivables_turnover",
            "payables_turnover",
            "inventory_turnover",
        ):
            ratio = ratio_bundle.by_code[ratio_code]
            if ratio.unavailable_reason:
                warnings.append(ratio.unavailable_reason)
            elif ratio.status_code in {"warning", "danger"}:
                warnings.append(f"{ratio.label}: {ratio.status_label}.")

        overdue_receivables = (
            snapshot.current_ar_aging_report.total_bucket_31_60
            + snapshot.current_ar_aging_report.total_bucket_61_90
            + snapshot.current_ar_aging_report.total_bucket_91_plus
        ).quantize(Decimal("0.01"))
        if overdue_receivables > _ZERO:
            warnings.append("Receivables aging already shows balances beyond 30 days overdue, reinforcing collection-cycle pressure.")

        return EfficiencyAnalysisDTO(
            cycle_ratios=(
                ratio_bundle.by_code["dso_days"],
                ratio_bundle.by_code["dpo_days"],
                ratio_bundle.by_code["dio_days"],
                ratio_bundle.by_code["cash_conversion_cycle"],
                ratio_bundle.by_code["receivables_turnover"],
                ratio_bundle.by_code["payables_turnover"],
                ratio_bundle.by_code["inventory_turnover"],
            ),
            warnings=tuple(dict.fromkeys(warnings)),
            interpretation_panel=interpretation_panel,
        )

    @staticmethod
    def _composition_row(
        *,
        component_code: str,
        label: str,
        amount: Decimal,
        total: Decimal,
        detail_key: str | None,
    ) -> WorkingCapitalCompositionRowDTO:
        return WorkingCapitalCompositionRowDTO(
            component_code=component_code,
            label=label,
            amount=amount,
            share_percent=to_ratio(safe_divide(amount, total)),
            detail_key=detail_key,
        )

    @staticmethod
    def _balance_detail_key(line_code: str, as_of_date) -> str | None:
        if as_of_date is None:
            return None
        return f"bs|{line_code}|{as_of_date.isoformat()}"
