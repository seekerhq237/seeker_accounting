from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AssetComponentDTO:
    id: int
    company_id: int
    parent_asset_id: int
    component_name: str
    acquisition_cost: Decimal
    salvage_value: Decimal | None
    useful_life_months: int
    depreciation_method_code: str
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
