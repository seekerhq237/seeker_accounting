from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PurchaseCreditNoteLineDTO:
    id: int
    line_number: int
    description: str
    quantity: Decimal | None
    unit_cost: Decimal | None
    expense_account_id: int | None
    expense_account_name: str | None
    tax_code_id: int | None
    tax_code_name: str | None
    line_subtotal_amount: Decimal
    line_tax_amount: Decimal
    line_total_amount: Decimal
    contract_id: int | None
    project_id: int | None
    project_job_id: int | None
    project_cost_code_id: int | None


@dataclass(frozen=True, slots=True)
class PurchaseCreditNoteListItemDTO:
    id: int
    credit_number: str
    supplier_id: int
    supplier_name: str
    supplier_credit_reference: str | None
    credit_date: date
    currency_code: str
    status_code: str
    total_amount: Decimal
    source_bill_id: int | None
    source_bill_number: str | None


@dataclass(frozen=True, slots=True)
class PurchaseCreditNoteDetailDTO:
    id: int
    company_id: int
    credit_number: str
    supplier_id: int
    supplier_name: str
    supplier_credit_reference: str | None
    credit_date: date
    currency_code: str
    exchange_rate: Decimal | None
    status_code: str
    reason_text: str | None
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    source_bill_id: int | None
    source_bill_number: str | None
    posted_journal_entry_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    contract_id: int | None
    project_id: int | None
    lines: list[PurchaseCreditNoteLineDTO]


@dataclass(frozen=True, slots=True)
class PurchasePostingCreditNoteResultDTO:
    credit_note_id: int
    credit_number: str
    journal_entry_id: int
    status_code: str
