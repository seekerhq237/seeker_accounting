from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CustomerGroupListItemDTO:
    id: int
    code: str
    name: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class CustomerGroupDTO:
    id: int
    company_id: int
    code: str
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerListItemDTO:
    id: int
    company_id: int
    customer_code: str
    display_name: str
    customer_group_id: int | None
    customer_group_name: str | None
    payment_term_id: int | None
    payment_term_name: str | None
    country_code: str | None
    credit_limit_amount: Decimal | None
    is_active: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerDetailDTO:
    id: int
    company_id: int
    customer_code: str
    display_name: str
    legal_name: str | None
    customer_group_id: int | None
    customer_group_name: str | None
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
    credit_limit_amount: Decimal | None
    is_active: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
