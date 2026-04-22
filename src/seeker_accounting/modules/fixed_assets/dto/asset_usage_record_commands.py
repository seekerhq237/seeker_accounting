from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateAssetUsageRecordCommand:
    usage_date: date
    units_used: Decimal
    notes: str | None = field(default=None)
