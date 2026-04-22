from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class AssetUsageRecordDTO:
    id: int
    company_id: int
    asset_id: int
    usage_date: date
    units_used: Decimal
    notes: str | None
    created_at: datetime
