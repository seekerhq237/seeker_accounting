from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FinancialAccountListItemDTO:
    id: int
    company_id: int
    account_code: str
    name: str
    financial_account_type_code: str
    gl_account_id: int
    gl_account_code: str
    gl_account_name: str
    currency_code: str
    is_active: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FinancialAccountDetailDTO:
    id: int
    company_id: int
    account_code: str
    name: str
    financial_account_type_code: str
    gl_account_id: int
    gl_account_code: str
    gl_account_name: str
    currency_code: str
    bank_name: str | None
    bank_account_number: str | None
    bank_branch: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

