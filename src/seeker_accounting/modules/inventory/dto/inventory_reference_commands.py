from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateUomCategoryCommand:
    code: str
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateUomCategoryCommand:
    code: str
    name: str
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class CreateUnitOfMeasureCommand:
    code: str
    name: str
    description: str | None = None
    category_id: int | None = None
    ratio_to_base: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class UpdateUnitOfMeasureCommand:
    code: str
    name: str
    description: str | None = None
    is_active: bool = True
    category_id: int | None = None
    ratio_to_base: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class CreateItemCategoryCommand:
    code: str
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateItemCategoryCommand:
    code: str
    name: str
    description: str | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class CreateInventoryLocationCommand:
    code: str
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateInventoryLocationCommand:
    code: str
    name: str
    description: str | None = None
    is_active: bool = True
