"""DTOs for the immutable stock ledger (Slice 2.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StockLedgerEntryDTO:
    """A single stock movement, fully self-describing including running totals."""

    id: int
    company_id: int
    item_id: int
    location_id: int | None
    posting_date: date
    document_type_code: str
    inventory_document_line_id: int | None
    direction: int
    quantity_base: Decimal
    unit_cost: Decimal
    value: Decimal
    running_quantity_after: Decimal
    running_value_after: Decimal
    running_avg_cost_after: Decimal


@dataclass(frozen=True, slots=True)
class StockLedgerPositionDTO:
    """Per-(item, location) position at a point in time."""

    company_id: int
    item_id: int
    location_id: int | None
    on_hand: Decimal
    value: Decimal
    avg_cost: Decimal
