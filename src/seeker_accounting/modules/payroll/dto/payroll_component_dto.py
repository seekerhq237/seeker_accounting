from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ── Read DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PayrollComponentListItemDTO:
    id: int
    company_id: int
    component_code: str
    component_name: str
    component_type_code: str
    calculation_method_code: str
    is_taxable: bool
    is_pensionable: bool
    expense_account_id: int | None
    expense_account_code: str | None
    liability_account_id: int | None
    liability_account_code: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class PayrollComponentDetailDTO:
    id: int
    company_id: int
    component_code: str
    component_name: str
    component_type_code: str
    calculation_method_code: str
    is_taxable: bool
    is_pensionable: bool
    expense_account_id: int | None
    expense_account_code: str | None
    expense_account_name: str | None
    liability_account_id: int | None
    liability_account_code: str | None
    liability_account_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Commands ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CreatePayrollComponentCommand:
    component_code: str
    component_name: str
    component_type_code: str
    calculation_method_code: str
    is_taxable: bool = field(default=False)
    is_pensionable: bool = field(default=False)
    expense_account_id: int | None = field(default=None)
    liability_account_id: int | None = field(default=None)


@dataclass(frozen=True, slots=True)
class UpdatePayrollComponentCommand:
    component_code: str
    component_name: str
    component_type_code: str
    calculation_method_code: str
    is_taxable: bool
    is_pensionable: bool
    is_active: bool
    expense_account_id: int | None = field(default=None)
    liability_account_id: int | None = field(default=None)
