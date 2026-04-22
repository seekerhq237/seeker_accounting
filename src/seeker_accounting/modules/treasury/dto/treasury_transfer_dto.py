from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TreasuryTransferListItemDTO:
    id: int
    company_id: int
    transfer_number: str
    from_financial_account_id: int
    from_account_name: str
    to_financial_account_id: int
    to_account_name: str
    transfer_date: date
    currency_code: str
    amount: Decimal
    status_code: str
    reference_number: str | None
    posted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TreasuryTransferDetailDTO:
    id: int
    company_id: int
    transfer_number: str
    from_financial_account_id: int
    from_account_name: str
    to_financial_account_id: int
    to_account_name: str
    transfer_date: date
    currency_code: str
    exchange_rate: Decimal | None
    amount: Decimal
    status_code: str
    reference_number: str | None
    description: str | None
    notes: str | None
    posted_journal_entry_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TreasuryTransferPostingResultDTO:
    company_id: int
    transfer_id: int
    transfer_number: str
    journal_entry_id: int
    journal_entry_number: str
    posted_at: datetime
    posted_by_user_id: int | None
