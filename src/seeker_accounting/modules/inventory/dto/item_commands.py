from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateItemCommand:
    item_code: str
    item_name: str
    item_type_code: str
    unit_of_measure_id: int
    unit_of_measure_code: str = "UNIT"
    item_category_id: int | None = None
    inventory_cost_method_code: str | None = None
    inventory_account_id: int | None = None
    cogs_account_id: int | None = None
    expense_account_id: int | None = None
    revenue_account_id: int | None = None
    purchase_tax_code_id: int | None = None
    sales_tax_code_id: int | None = None
    reorder_level_quantity: Decimal | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateItemCommand:
    item_code: str
    item_name: str
    item_type_code: str
    unit_of_measure_id: int
    unit_of_measure_code: str = "UNIT"
    item_category_id: int | None = None
    inventory_cost_method_code: str | None = None
    inventory_account_id: int | None = None
    cogs_account_id: int | None = None
    expense_account_id: int | None = None
    revenue_account_id: int | None = None
    purchase_tax_code_id: int | None = None
    sales_tax_code_id: int | None = None
    reorder_level_quantity: Decimal | None = None
    description: str | None = None
    is_active: bool = True
