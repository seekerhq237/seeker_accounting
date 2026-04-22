from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SupplierGroupListItemDTO:
    id: int
    code: str
    name: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class SupplierGroupDTO:
    id: int
    company_id: int
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SupplierListItemDTO:
    id: int
    company_id: int
    supplier_code: str
    display_name: str
    supplier_group_id: int | None
    supplier_group_name: str | None
    payment_term_id: int | None
    payment_term_name: str | None
    country_code: str | None
    is_active: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SupplierDetailDTO:
    id: int
    company_id: int
    supplier_code: str
    display_name: str
    legal_name: str | None
    supplier_group_id: int | None
    supplier_group_name: str | None
    payment_term_id: int | None
    payment_term_name: str | None
    tax_identifier: str | None
    phone: str | None
    email: str | None
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    region: str | None
    country_code: str | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
