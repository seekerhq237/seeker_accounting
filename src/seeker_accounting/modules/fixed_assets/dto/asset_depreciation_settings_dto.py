from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AssetDepreciationSettingsDTO:
    id: int
    company_id: int
    asset_id: int
    declining_factor: Decimal | None
    switch_to_straight_line: bool
    expected_total_units: Decimal | None
    interest_rate: Decimal | None
    macrs_profile_id: int | None
    macrs_convention_code: str | None
    created_at: datetime
    updated_at: datetime
