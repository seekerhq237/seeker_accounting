from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.interpretation_dto import InterpretationPanelDTO


@dataclass(frozen=True, slots=True)
class TrendPointDTO:
    label: str
    value: Decimal | None
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class TrendSeriesDTO:
    metric_code: str
    label: str
    color_name: str
    points: tuple[TrendPointDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class VarianceRowDTO:
    metric_code: str
    label: str
    current_value: Decimal | None
    prior_value: Decimal | None
    variance_value: Decimal | None
    variance_percent: Decimal | None
    status_code: str
    detail_key: str | None = None
    basis_note: str | None = None


@dataclass(frozen=True, slots=True)
class CompositionVarianceRowDTO:
    component_code: str
    label: str
    current_value: Decimal | None
    prior_value: Decimal | None
    variance_value: Decimal | None
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class TrendDetailDTO:
    metric_code: str
    title: str
    subtitle: str
    series: tuple[TrendSeriesDTO, ...] = field(default_factory=tuple)
    variance_rows: tuple[VarianceRowDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TrendAnalysisDTO:
    series: tuple[TrendSeriesDTO, ...] = field(default_factory=tuple)
    variance_rows: tuple[VarianceRowDTO, ...] = field(default_factory=tuple)
    composition_rows: tuple[CompositionVarianceRowDTO, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    interpretation_panel: InterpretationPanelDTO | None = None
