from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReferenceOptionDTO:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class PaymentTermListItemDTO:
    id: int
    code: str
    name: str
    days_due: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class PaymentTermDTO:
    id: int
    company_id: int
    code: str
    name: str
    days_due: int
    description: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class AccountClassDTO:
    id: int
    code: str
    name: str
    display_order: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class AccountTypeDTO:
    id: int
    code: str
    name: str
    normal_balance: str
    financial_statement_section_code: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class CreatePaymentTermCommand:
    code: str
    name: str
    days_due: int
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdatePaymentTermCommand:
    code: str
    name: str
    days_due: int
    description: str | None = None
