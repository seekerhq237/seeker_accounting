"""Stock reservation DTOs.

Per Slice 2.4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateReservationCommand:
    item_id: int
    location_id: int | None
    quantity: Decimal
    source_module: str
    source_document_id: int | None
    source_document_line_id: int | None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StockReservationDTO:
    id: int
    company_id: int
    item_id: int
    location_id: int | None
    quantity: Decimal
    source_module: str
    source_document_id: int | None
    source_document_line_id: int | None
    status_code: str
    expires_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StockPositionDTO:
    """Full ATP position for a (company, item, location).

    Per Slice 2.4: ``available = on_hand - reserved``.
    ``on_order`` is not managed by this slice — callers may provide a value
    or leave it as ``Decimal('0.0000')``.
    """

    company_id: int
    item_id: int
    location_id: int | None
    on_hand: Decimal
    value: Decimal
    avg_cost: Decimal
    reserved: Decimal
    on_order: Decimal

    @property
    def available(self) -> Decimal:
        return max(self.on_hand - self.reserved, Decimal("0.0000"))
