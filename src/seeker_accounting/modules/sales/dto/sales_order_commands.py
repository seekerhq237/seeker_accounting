from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SalesOrderLineCommand:
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_code_id: int | None = None
    revenue_account_id: int | None = None
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreateSalesOrderCommand:
    customer_id: int
    order_date: date
    requested_delivery_date: date | None = None
    currency_code: str = ""
    exchange_rate: Decimal | None = None
    reference_number: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    source_quote_id: int | None = None
    lines: tuple[SalesOrderLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateSalesOrderCommand:
    customer_id: int
    order_date: date
    requested_delivery_date: date | None = None
    currency_code: str = ""
    exchange_rate: Decimal | None = None
    reference_number: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[SalesOrderLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class ConvertSalesOrderCommand:
    invoice_date: date
    due_date: date
    reference_number: str | None = None
    notes: str | None = None
    actor_user_id: int | None = None
