from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ComparativeMetricDTO:
    key: str
    label: str
    current_value: Decimal | None
    prior_value: Decimal | None
    variance_value: Decimal | None
    variance_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class ComparativeAnalysisDTO:
    current_label: str
    prior_label: str
    metrics: tuple[ComparativeMetricDTO, ...] = field(default_factory=tuple)
    limitation_message: str | None = None
