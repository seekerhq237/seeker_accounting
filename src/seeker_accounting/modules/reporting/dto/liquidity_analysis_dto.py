from __future__ import annotations

from dataclasses import dataclass, field

from seeker_accounting.modules.reporting.dto.interpretation_dto import InterpretationPanelDTO
from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioResultDTO
from seeker_accounting.modules.reporting.dto.working_capital_dto import WorkingCapitalAnalysisDTO


@dataclass(frozen=True, slots=True)
class LiquidityAnalysisDTO:
    working_capital_analysis: WorkingCapitalAnalysisDTO
    liquidity_ratios: tuple[RatioResultDTO, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    interpretation_panel: InterpretationPanelDTO | None = None
