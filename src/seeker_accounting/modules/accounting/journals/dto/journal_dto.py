from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class JournalLineDTO:
    id: int
    line_number: int
    account_id: int
    account_code: str
    account_name: str
    line_description: str | None
    debit_amount: Decimal
    credit_amount: Decimal
    created_at: datetime
    updated_at: datetime
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class JournalTotalsDTO:
    total_debit: Decimal
    total_credit: Decimal
    imbalance_amount: Decimal
    is_balanced: bool


@dataclass(frozen=True, slots=True)
class JournalEntryListItemDTO:
    id: int
    company_id: int
    fiscal_period_id: int
    fiscal_period_code: str
    entry_number: str | None
    entry_date: date
    transaction_date: date | None
    journal_type_code: str
    reference_text: str | None
    description: str | None
    status_code: str
    total_debit: Decimal
    total_credit: Decimal
    is_balanced: bool
    posted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class JournalEntryDetailDTO:
    id: int
    company_id: int
    fiscal_period_id: int
    fiscal_period_code: str
    entry_number: str | None
    entry_date: date
    transaction_date: date | None
    journal_type_code: str
    reference_text: str | None
    description: str | None
    source_module_code: str | None
    source_document_type: str | None
    source_document_id: int | None
    status_code: str
    posted_at: datetime | None
    posted_by_user_id: int | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    totals: JournalTotalsDTO
    lines: tuple[JournalLineDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class JournalPostResultDTO:
    journal_entry_id: int
    company_id: int
    fiscal_period_id: int
    fiscal_period_code: str
    entry_number: str
    entry_date: date
    transaction_date: date | None
    status_code: str
    posted_at: datetime
    posted_by_user_id: int | None
