from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class UomCategoryDTO:
    id: int
    company_id: int
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UnitOfMeasureDTO:
    id: int
    company_id: int
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    category_id: int | None = None
    category_code: str | None = None
    category_name: str | None = None
    ratio_to_base: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class ItemCategoryDTO:
    id: int
    company_id: int
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class InventoryLocationDTO:
    id: int
    company_id: int
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
