from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateAssetComponentCommand:
    component_name: str
    acquisition_cost: Decimal
    useful_life_months: int
    depreciation_method_code: str
    salvage_value: Decimal | None = field(default=None)
    notes: str | None = field(default=None)


@dataclass(frozen=True, slots=True)
class UpdateAssetComponentCommand:
    component_name: str
    acquisition_cost: Decimal
    useful_life_months: int
    depreciation_method_code: str
    salvage_value: Decimal | None = field(default=None)
    notes: str | None = field(default=None)
    is_active: bool = field(default=True)
