from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InventoryStockPositionDTO:
    item_id: int
    item_code: str
    item_name: str
    unit_of_measure_code: str
    quantity_on_hand: Decimal
    total_value: Decimal
    weighted_average_cost: Decimal | None
    reorder_level_quantity: Decimal | None
    is_low_stock: bool


@dataclass(frozen=True, slots=True)
class InventoryValuationSummaryDTO:
    total_items_with_stock: int
    total_quantity_on_hand: Decimal
    total_inventory_value: Decimal
    low_stock_item_count: int
