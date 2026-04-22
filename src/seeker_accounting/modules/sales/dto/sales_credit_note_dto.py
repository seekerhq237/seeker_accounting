from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SalesCreditNoteLineDTO:
    id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal | None
    discount_amount: Decimal | None
    tax_code_id: int | None
    tax_code_name: str | None
    revenue_account_id: int
    revenue_account_name: str
    line_subtotal_amount: Decimal
    line_tax_amount: Decimal
    line_total_amount: Decimal
    contract_id: int | None
    project_id: int | None
    project_job_id: int | None
    project_cost_code_id: int | None


@dataclass(frozen=True, slots=True)
class SalesCreditNoteListItemDTO:
    id: int
    credit_number: str
    customer_id: int
    customer_name: str
    credit_date: date
    currency_code: str
    status_code: str
    total_amount: Decimal
    source_invoice_id: int | None
    source_invoice_number: str | None


@dataclass(frozen=True, slots=True)
class SalesCreditNoteDetailDTO:
    id: int
    company_id: int
    credit_number: str
    customer_id: int
    customer_name: str
    credit_date: date
    currency_code: str
    exchange_rate: Decimal | None
    status_code: str
    reason_text: str | None
    reference_number: str | None
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    source_invoice_id: int | None
    source_invoice_number: str | None
    posted_journal_entry_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    contract_id: int | None
    project_id: int | None
    lines: list[SalesCreditNoteLineDTO]


@dataclass(frozen=True, slots=True)
class SalesPostingCreditNoteResultDTO:
    credit_note_id: int
    credit_number: str
    journal_entry_id: int
    status_code: str
