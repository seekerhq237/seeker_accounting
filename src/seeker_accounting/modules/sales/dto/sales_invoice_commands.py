from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SalesInvoiceLineCommand:
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_code_id: int | None = None
    revenue_account_id: int = 0
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreateSalesInvoiceCommand:
    customer_id: int
    invoice_date: date
    due_date: date
    currency_code: str
    exchange_rate: Decimal | None = None
    reference_number: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[SalesInvoiceLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateSalesInvoiceCommand:
    customer_id: int
    invoice_date: date
    due_date: date
    currency_code: str
    exchange_rate: Decimal | None = None
    reference_number: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[SalesInvoiceLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class PostSalesInvoiceCommand:
    actor_user_id: int | None = None

