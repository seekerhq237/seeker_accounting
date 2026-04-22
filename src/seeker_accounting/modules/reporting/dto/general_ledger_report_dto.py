from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GeneralLedgerLineDTO:
    line_id: int
    journal_entry_id: int
    line_number: int
    entry_date: date
    entry_number: str | None
    reference_text: str | None
    journal_description: str | None
    line_description: str | None
    debit_amount: Decimal
    credit_amount: Decimal
    running_balance: Decimal
    source_module_code: str | None
    source_document_type: str | None
    source_document_id: int | None
    posted_at: datetime | None


@dataclass(frozen=True, slots=True)
class GeneralLedgerAccountDTO:
    account_id: int
    account_code: str
    account_name: str
    opening_debit: Decimal
    opening_credit: Decimal
    opening_balance: Decimal
    period_debit: Decimal
    period_credit: Decimal
    closing_debit: Decimal
    closing_credit: Decimal
    closing_balance: Decimal
    total_debit: Decimal
    total_credit: Decimal
    lines: tuple[GeneralLedgerLineDTO, ...]


@dataclass(frozen=True, slots=True)
class GeneralLedgerReportDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    accounts: tuple[GeneralLedgerAccountDTO, ...]
