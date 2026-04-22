from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class AssetDepreciationPoolMemberDTO:
    id: int
    pool_id: int
    asset_id: int
    joined_date: date
    left_date: date | None


@dataclass(frozen=True, slots=True)
class AssetDepreciationPoolDTO:
    id: int
    company_id: int
    code: str
    name: str
    pool_type_code: str
    depreciation_method_code: str
    useful_life_months: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    members: tuple[AssetDepreciationPoolMemberDTO, ...]
