from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CustomerReceiptAllocationCommand:
    sales_invoice_id: int
    allocated_amount: Decimal


@dataclass(frozen=True, slots=True)
class CreateCustomerReceiptCommand:
    customer_id: int
    financial_account_id: int
    receipt_date: date
    currency_code: str
    exchange_rate: Decimal | None = None
    amount_received: Decimal = Decimal("0.00")
    reference_number: str | None = None
    notes: str | None = None
    allocations: tuple[CustomerReceiptAllocationCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateCustomerReceiptCommand:
    customer_id: int
    financial_account_id: int
    receipt_date: date
    currency_code: str
    exchange_rate: Decimal | None = None
    amount_received: Decimal = Decimal("0.00")
    reference_number: str | None = None
    notes: str | None = None
    allocations: tuple[CustomerReceiptAllocationCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class PostCustomerReceiptCommand:
    actor_user_id: int | None = None

