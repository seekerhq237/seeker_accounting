from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateCustomerGroupCommand:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class UpdateCustomerGroupCommand:
    code: str
    name: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class CreateCustomerCommand:
    customer_code: str
    display_name: str
    legal_name: str | None = None
    customer_group_id: int | None = None
    payment_term_id: int | None = None
    tax_identifier: str | None = None
    phone: str | None = None
    email: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    credit_limit_amount: Decimal | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateCustomerCommand:
    customer_code: str
    display_name: str
    legal_name: str | None = None
    customer_group_id: int | None = None
    payment_term_id: int | None = None
    tax_identifier: str | None = None
    phone: str | None = None
    email: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    country_code: str | None = None
    credit_limit_amount: Decimal | None = None
    is_active: bool = True
    notes: str | None = None
