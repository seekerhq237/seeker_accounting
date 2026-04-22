from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ItemListItemDTO:
    id: int
    company_id: int
    item_code: str
    item_name: str
    item_type_code: str
    unit_of_measure_code: str
    unit_of_measure_id: int | None
    item_category_id: int | None
    inventory_cost_method_code: str | None
    reorder_level_quantity: Decimal | None
    is_active: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ItemDetailDTO:
    id: int
    company_id: int
    item_code: str
    item_name: str
    item_type_code: str
    unit_of_measure_code: str
    unit_of_measure_id: int | None
    item_category_id: int | None
    inventory_cost_method_code: str | None
    inventory_account_id: int | None
    cogs_account_id: int | None
    expense_account_id: int | None
    revenue_account_id: int | None
    purchase_tax_code_id: int | None
    sales_tax_code_id: int | None
    reorder_level_quantity: Decimal | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
