from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RatioTrendPointDTO:
    label: str
    value: Decimal | None
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class RatioComponentDTO:
    label: str
    amount: Decimal | None
    source_label: str
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class RatioResultDTO:
    ratio_code: str
    label: str
    category_code: str
    formula_label: str
    display_value: str
    value: Decimal | None
    status_code: str
    status_label: str
    as_of_date: date | None
    numerator_label: str | None = None
    denominator_label: str | None = None
    numerator_value: Decimal | None = None
    denominator_value: Decimal | None = None
    prior_value: Decimal | None = None
    prior_display_value: str | None = None
    change_value: Decimal | None = None
    change_percent: Decimal | None = None
    change_label: str | None = None
    basis_note: str | None = None
    unavailable_reason: str | None = None
    detail_key: str | None = None
    source_detail_keys: tuple[str, ...] = field(default_factory=tuple)
    components: tuple[RatioComponentDTO, ...] = field(default_factory=tuple)
    trend_points: tuple[RatioTrendPointDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RatioDetailDTO:
    ratio_code: str
    title: str
    subtitle: str
    formula_label: str
    value_text: str
    status_label: str
    basis_note: str | None = None
    comparison_text: str | None = None
    unavailable_reason: str | None = None
    components: tuple[RatioComponentDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RatioAnalysisBundleDTO:
    ratios: tuple[RatioResultDTO, ...] = field(default_factory=tuple)
    by_code: dict[str, RatioResultDTO] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)
