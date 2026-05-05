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
    unit_of_measure_id: int
    item_category_id: int | None
    parent_item_id: int | None
    inventory_cost_method_code: str | None
    lifecycle_status_code: str
    tracking_mode_code: str
    is_variant: bool
    is_sellable: bool
    is_purchasable: bool
    is_stockable: bool
    ohada_stock_class_code: str | None
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
    unit_of_measure_id: int
    item_category_id: int | None
    parent_item_id: int | None
    inventory_cost_method_code: str | None
    standard_cost: Decimal | None
    lifecycle_status_code: str
    tracking_mode_code: str
    is_variant: bool
    attribute_values_json: str | None
    is_sellable: bool
    is_purchasable: bool
    is_stockable: bool
    ohada_stock_class_code: str | None
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


@dataclass(frozen=True, slots=True)
class ItemUomConversionDTO:
    """Per-item UoM conversion row exposed to UI / services."""

    id: int
    item_id: int
    unit_of_measure_id: int
    unit_of_measure_code: str
    ratio_to_base: Decimal
    rounding_rule_code: str
    min_increment: Decimal | None
    is_purchase_default: bool
    is_sales_default: bool
    is_stocking: bool
    is_active: bool


@dataclass(frozen=True, slots=True)
class ItemAccountOverrideDTO:
    id: int
    item_id: int
    location_id: int | None
    location_code: str | None
    inventory_account_id: int | None
    cogs_account_id: int | None
    expense_account_id: int | None
    revenue_account_id: int | None


@dataclass(frozen=True, slots=True)
class ResolvedItemAccountsDTO:
    """Outcome of :meth:`ItemAccountResolverService.resolve_accounts`.

    ``inventory_account_id`` is the only account that is required to be
    populated for stockable postings; the others may be ``None`` if the
    requested operation does not need them.
    """

    item_id: int
    location_id: int | None
    inventory_account_id: int | None
    cogs_account_id: int | None
    expense_account_id: int | None
    revenue_account_id: int | None
