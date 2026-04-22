from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TreasuryTransactionLineDTO:
    id: int
    line_number: int
    account_id: int
    account_code: str
    account_name: str
    line_description: str
    party_type: str | None
    party_id: int | None
    tax_code_id: int | None
    tax_code_code: str | None
    amount: Decimal
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class TreasuryTransactionListItemDTO:
    id: int
    company_id: int
    transaction_number: str
    transaction_type_code: str
    financial_account_id: int
    financial_account_name: str
    transaction_date: date
    currency_code: str
    total_amount: Decimal
    status_code: str
    reference_number: str | None
    posted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TreasuryTransactionDetailDTO:
    id: int
    company_id: int
    transaction_number: str
    transaction_type_code: str
    financial_account_id: int
    financial_account_name: str
    transaction_date: date
    currency_code: str
    exchange_rate: Decimal | None
    total_amount: Decimal
    status_code: str
    reference_number: str | None
    description: str | None
    notes: str | None
    posted_journal_entry_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[TreasuryTransactionLineDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TreasuryTransactionPostingResultDTO:
    company_id: int
    transaction_id: int
    transaction_number: str
    journal_entry_id: int
    journal_entry_number: str
    posted_at: datetime
    posted_by_user_id: int | None
