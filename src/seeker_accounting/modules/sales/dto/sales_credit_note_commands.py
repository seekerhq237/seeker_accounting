from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SalesCreditNoteLineCommand:
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal | None
    tax_code_id: int | None
    revenue_account_id: int
    contract_id: int | None
    project_id: int | None
    project_job_id: int | None
    project_cost_code_id: int | None


@dataclass(frozen=True, slots=True)
class CreateSalesCreditNoteCommand:
    company_id: int
    customer_id: int
    credit_date: date
    currency_code: str
    exchange_rate: Decimal | None
    reason_text: str | None
    reference_number: str | None
    source_invoice_id: int | None
    contract_id: int | None
    project_id: int | None
    lines: list[SalesCreditNoteLineCommand]
    actor_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class UpdateSalesCreditNoteCommand:
    credit_note_id: int
    company_id: int
    customer_id: int
    credit_date: date
    currency_code: str
    exchange_rate: Decimal | None
    reason_text: str | None
    reference_number: str | None
    source_invoice_id: int | None
    contract_id: int | None
    project_id: int | None
    lines: list[SalesCreditNoteLineCommand]
    actor_user_id: int | None = None
