from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.interpretation_dto import InterpretationPanelDTO
from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioResultDTO


@dataclass(frozen=True, slots=True)
class CapitalStructureSliceDTO:
    slice_code: str
    label: str
    amount: Decimal
    share_percent: Decimal | None
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class SolvencyAnalysisDTO:
    solvency_ratios: tuple[RatioResultDTO, ...] = field(default_factory=tuple)
    capital_structure_rows: tuple[CapitalStructureSliceDTO, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    interpretation_panel: InterpretationPanelDTO | None = None
