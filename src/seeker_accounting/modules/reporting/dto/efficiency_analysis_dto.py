from __future__ import annotations

from dataclasses import dataclass, field

from seeker_accounting.modules.reporting.dto.interpretation_dto import InterpretationPanelDTO
from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioResultDTO


@dataclass(frozen=True, slots=True)
class EfficiencyAnalysisDTO:
    cycle_ratios: tuple[RatioResultDTO, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    interpretation_panel: InterpretationPanelDTO | None = None
