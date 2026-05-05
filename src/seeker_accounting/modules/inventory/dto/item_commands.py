from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateItemCommand:
    item_code: str
    item_name: str
    item_type_code: str
    unit_of_measure_id: int
    # ``unit_of_measure_code`` is kept for backwards compatibility with existing
    # callers (the new-item wizard, smoke scripts) but is now ignored — the
    # canonical UoM identity is ``unit_of_measure_id``.
    unit_of_measure_code: str = "UNIT"
    item_category_id: int | None = None
    inventory_cost_method_code: str | None = None
    standard_cost: Decimal | None = None
    lifecycle_status_code: str = "active"
    tracking_mode_code: str = "none"
    parent_item_id: int | None = None
    is_variant: bool = False
    attribute_values_json: str | None = None
    is_sellable: bool = True
    is_purchasable: bool = True
    is_stockable: bool = True
    ohada_stock_class_code: str | None = None
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
    standard_cost: Decimal | None = None
    lifecycle_status_code: str = "active"
    tracking_mode_code: str = "none"
    parent_item_id: int | None = None
    is_variant: bool = False
    attribute_values_json: str | None = None
    is_sellable: bool = True
    is_purchasable: bool = True
    is_stockable: bool = True
    ohada_stock_class_code: str | None = None
    inventory_account_id: int | None = None
    cogs_account_id: int | None = None
    expense_account_id: int | None = None
    revenue_account_id: int | None = None
    purchase_tax_code_id: int | None = None
    sales_tax_code_id: int | None = None
    reorder_level_quantity: Decimal | None = None
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class CreateItemUomConversionCommand:
    item_id: int
    unit_of_measure_id: int
    ratio_to_base: Decimal
    rounding_rule_code: str = "none"
    min_increment: Decimal | None = None
    is_purchase_default: bool = False
    is_sales_default: bool = False
    is_stocking: bool = True


@dataclass(frozen=True, slots=True)
class UpdateItemUomConversionCommand:
    conversion_id: int
    ratio_to_base: Decimal
    rounding_rule_code: str
    min_increment: Decimal | None = None
    is_purchase_default: bool = False
    is_sales_default: bool = False
    is_stocking: bool = True
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class CreateItemAccountOverrideCommand:
    item_id: int
    location_id: int | None = None
    inventory_account_id: int | None = None
    cogs_account_id: int | None = None
    expense_account_id: int | None = None
    revenue_account_id: int | None = None
