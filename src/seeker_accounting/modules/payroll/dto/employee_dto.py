from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


# ── Read DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EmployeeListItemDTO:
    id: int
    company_id: int
    employee_number: str
    display_name: str
    first_name: str
    last_name: str
    department_id: int | None
    department_name: str | None
    position_id: int | None
    position_name: str | None
    hire_date: date
    termination_date: date | None
    base_currency_code: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class EmployeeDetailDTO:
    id: int
    company_id: int
    employee_number: str
    display_name: str
    first_name: str
    last_name: str
    department_id: int | None
    department_name: str | None
    position_id: int | None
    position_name: str | None
    hire_date: date
    termination_date: date | None
    phone: str | None
    email: str | None
    tax_identifier: str | None
    cnps_number: str | None
    default_payment_account_id: int | None
    base_currency_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Commands ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CreateEmployeeCommand:
    employee_number: str
    display_name: str
    first_name: str
    last_name: str
    hire_date: date
    base_currency_code: str
    department_id: int | None = field(default=None)
    position_id: int | None = field(default=None)
    termination_date: date | None = field(default=None)
    phone: str | None = field(default=None)
    email: str | None = field(default=None)
    tax_identifier: str | None = field(default=None)
    cnps_number: str | None = field(default=None)
    default_payment_account_id: int | None = field(default=None)


@dataclass(frozen=True, slots=True)
class UpdateEmployeeCommand:
    employee_number: str
    display_name: str
    first_name: str
    last_name: str
    hire_date: date
    base_currency_code: str
    is_active: bool
    department_id: int | None = field(default=None)
    position_id: int | None = field(default=None)
    termination_date: date | None = field(default=None)
    phone: str | None = field(default=None)
    email: str | None = field(default=None)
    tax_identifier: str | None = field(default=None)
