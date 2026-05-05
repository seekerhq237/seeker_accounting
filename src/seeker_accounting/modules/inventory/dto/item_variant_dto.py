from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand


@dataclass(frozen=True, slots=True)
class CreateItemAttributeDefinitionCommand:
    attribute_code: str
    attribute_name: str
    item_category_id: int | None = None
    allowed_values_json: str | None = None
    sort_order: int = 0


@dataclass(frozen=True, slots=True)
class UpdateItemAttributeDefinitionCommand:
    attribute_id: int
    attribute_code: str
    attribute_name: str
    item_category_id: int | None = None
    allowed_values_json: str | None = None
    sort_order: int = 0
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class CreateItemVariantCommand:
    parent_item_id: int
    child_item: CreateItemCommand
    attribute_values_json: str
    variant_sku_suffix: str | None = None


@dataclass(frozen=True, slots=True)
class ItemAttributeDefinitionDTO:
    id: int
    company_id: int
    item_category_id: int | None
    attribute_code: str
    attribute_name: str
    allowed_values_json: str | None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ItemVariantDTO:
    id: int
    company_id: int
    parent_item_id: int
    child_item_id: int
    child_item_code: str
    child_item_name: str
    attribute_value_combination_hash: str
    attribute_values_json: str
    variant_sku_suffix: str | None
    status_code: str
    created_at: datetime
    updated_at: datetime