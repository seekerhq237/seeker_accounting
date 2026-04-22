from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from seeker_accounting.modules.reporting.dto.efficiency_analysis_dto import EfficiencyAnalysisDTO
from seeker_accounting.modules.reporting.dto.insight_card_dto import InsightCardDTO
from seeker_accounting.modules.reporting.dto.liquidity_analysis_dto import LiquidityAnalysisDTO
from seeker_accounting.modules.reporting.dto.profitability_analysis_dto import ProfitabilityAnalysisDTO
from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioResultDTO
from seeker_accounting.modules.reporting.dto.solvency_analysis_dto import SolvencyAnalysisDTO
from seeker_accounting.modules.reporting.dto.trend_analysis_dto import TrendAnalysisDTO


@dataclass(frozen=True, slots=True)
class FinancialAnalysisOverviewDTO:
    headline_ratios: tuple[RatioResultDTO, ...] = field(default_factory=tuple)
    warning_insights: tuple[InsightCardDTO, ...] = field(default_factory=tuple)
    strength_insights: tuple[InsightCardDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class FinancialAnalysisWorkspaceDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    period_label: str
    overview: FinancialAnalysisOverviewDTO
    liquidity: LiquidityAnalysisDTO
    efficiency: EfficiencyAnalysisDTO
    profitability: ProfitabilityAnalysisDTO
    solvency: SolvencyAnalysisDTO
    trend: TrendAnalysisDTO
    management_insights: tuple[InsightCardDTO, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
