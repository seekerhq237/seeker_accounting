from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class CreateAssetDepreciationPoolCommand:
    code: str
    name: str
    pool_type_code: str  # group | composite
    depreciation_method_code: str
    useful_life_months: int


@dataclass(frozen=True, slots=True)
class UpdateAssetDepreciationPoolCommand:
    name: str
    depreciation_method_code: str
    useful_life_months: int
    is_active: bool = field(default=True)


@dataclass(frozen=True, slots=True)
class AddPoolMemberCommand:
    asset_id: int
    joined_date: date
