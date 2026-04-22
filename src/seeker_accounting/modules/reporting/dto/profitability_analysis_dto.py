from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.interpretation_dto import InterpretationPanelDTO
from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioResultDTO


@dataclass(frozen=True, slots=True)
class ExpenseStructureRowDTO:
    component_code: str
    label: str
    amount: Decimal
    share_of_revenue: Decimal | None
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class ProfitabilityAnalysisDTO:
    profitability_ratios: tuple[RatioResultDTO, ...] = field(default_factory=tuple)
    expense_structure_rows: tuple[ExpenseStructureRowDTO, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    interpretation_panel: InterpretationPanelDTO | None = None
