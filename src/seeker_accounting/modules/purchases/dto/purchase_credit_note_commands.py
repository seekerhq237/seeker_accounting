from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PurchaseCreditNoteLineCommand:
    description: str
    quantity: Decimal | None
    unit_cost: Decimal | None
    expense_account_id: int | None
    tax_code_id: int | None
    line_subtotal_amount: Decimal
    contract_id: int | None
    project_id: int | None
    project_job_id: int | None
    project_cost_code_id: int | None


@dataclass(frozen=True, slots=True)
class CreatePurchaseCreditNoteCommand:
    company_id: int
    supplier_id: int
    supplier_credit_reference: str | None
    credit_date: date
    currency_code: str
    exchange_rate: Decimal | None
    reason_text: str | None
    source_bill_id: int | None
    contract_id: int | None
    project_id: int | None
    lines: list[PurchaseCreditNoteLineCommand]
    actor_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class UpdatePurchaseCreditNoteCommand:
    credit_note_id: int
    company_id: int
    supplier_id: int
    supplier_credit_reference: str | None
    credit_date: date
    currency_code: str
    exchange_rate: Decimal | None
    reason_text: str | None
    source_bill_id: int | None
    contract_id: int | None
    project_id: int | None
    lines: list[PurchaseCreditNoteLineCommand]
    actor_user_id: int | None = None
