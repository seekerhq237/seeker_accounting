from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateFinancialAccountCommand:
    account_code: str
    name: str
    financial_account_type_code: str
    gl_account_id: int
    currency_code: str
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_branch: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateFinancialAccountCommand:
    account_code: str
    name: str
    financial_account_type_code: str
    gl_account_id: int
    currency_code: str
    bank_name: str | None = None
    bank_account_number: str | None = None
    bank_branch: str | None = None
    is_active: bool = True

