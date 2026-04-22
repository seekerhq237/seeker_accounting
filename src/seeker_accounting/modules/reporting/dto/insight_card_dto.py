from __future__ import annotations

from dataclasses import dataclass, field

from seeker_accounting.modules.reporting.dto.ratio_analysis_dto import RatioResultDTO


@dataclass(frozen=True, slots=True)
class InsightNumericBasisDTO:
    label: str
    value_text: str
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class InsightCardDTO:
    insight_code: str
    title: str
    statement: str
    why_it_matters: str
    severity_code: str
    importance_rank: int
    numeric_basis: tuple[InsightNumericBasisDTO, ...] = field(default_factory=tuple)
    comparison_text: str | None = None
    detail_key: str | None = None
    related_ratio_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class InsightDetailDTO:
    period_label: str
    card: InsightCardDTO
    related_ratios: tuple[RatioResultDTO, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
