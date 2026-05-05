from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BomComponentCommand:
    component_item_id: int
    quantity_per: Decimal
    sequence: int | None = None
    scrap_percent: Decimal = Decimal("0")
    uom_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CreateBillOfMaterialCommand:
    item_id: int
    version: str
    type_code: str = "assembly"
    effective_from: date | None = None
    effective_to: date | None = None
    overhead_per_unit: Decimal | None = None
    notes: str | None = None
    components: tuple[BomComponentCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateBillOfMaterialCommand:
    bom_id: int
    version: str
    type_code: str
    status_code: str
    effective_from: date | None = None
    effective_to: date | None = None
    overhead_per_unit: Decimal | None = None
    notes: str | None = None
    components: tuple[BomComponentCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class BomComponentDTO:
    id: int
    bom_id: int
    sequence: int
    component_item_id: int
    quantity_per: Decimal
    scrap_percent: Decimal
    uom_id: int | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class BillOfMaterialDTO:
    id: int
    company_id: int
    item_id: int
    version: str
    status_code: str
    type_code: str
    effective_from: date | None
    effective_to: date | None
    overhead_per_unit: Decimal | None
    notes: str | None
    approved_at: datetime | None
    approved_by_user_id: int | None
    components: tuple[BomComponentDTO, ...]