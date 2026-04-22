from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateSupplierGroupCommand:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class UpdateSupplierGroupCommand:
    code: str
    name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class CreateSupplierCommand:
    supplier_code: str
    display_name: str
    legal_name: str | None = None
    supplier_group_id: int | None = None
    payment_term_id: int | None = None
    tax_identifier: str | None = None
    phone: str | None = None
    email: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateSupplierCommand:
    supplier_code: str
    display_name: str
    legal_name: str | None = None
    supplier_group_id: int | None = None
    payment_term_id: int | None = None
    tax_identifier: str | None = None
    phone: str | None = None
    email: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    is_active: bool = True
    notes: str | None = None
