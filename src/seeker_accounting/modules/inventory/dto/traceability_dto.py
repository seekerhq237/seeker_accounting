from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class CreateItemBatchCommand:
    item_id: int
    batch_number: str
    manufactured_on: date | None = None
    expiry_on: date | None = None
    supplier_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateItemBatchCommand:
    batch_id: int
    batch_number: str
    status_code: str
    manufactured_on: date | None = None
    expiry_on: date | None = None
    supplier_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ItemBatchDTO:
    id: int
    company_id: int
    item_id: int
    batch_number: str
    status_code: str
    manufactured_on: date | None
    expiry_on: date | None
    supplier_id: int | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class CreateItemSerialCommand:
    item_id: int
    serial_number: str
    batch_id: int | None = None
    warranty_until: date | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateItemSerialCommand:
    serial_id: int
    serial_number: str
    status_code: str
    batch_id: int | None = None
    current_location_id: int | None = None
    warranty_until: date | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ItemSerialDTO:
    id: int
    company_id: int
    item_id: int
    serial_number: str
    status_code: str
    batch_id: int | None
    current_location_id: int | None
    current_doc_line_id: int | None
    warranty_until: date | None
    notes: str | None