from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SupplierPaymentAllocationCommand:
    purchase_bill_id: int
    allocated_amount: Decimal


@dataclass(frozen=True, slots=True)
class CreateSupplierPaymentCommand:
    supplier_id: int
    financial_account_id: int
    payment_date: date
    currency_code: str
    exchange_rate: Decimal | None = None
    amount_paid: Decimal = Decimal("0.00")
    reference_number: str | None = None
    notes: str | None = None
    allocations: tuple[SupplierPaymentAllocationCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateSupplierPaymentCommand:
    supplier_id: int
    financial_account_id: int
    payment_date: date
    currency_code: str
    exchange_rate: Decimal | None = None
    amount_paid: Decimal = Decimal("0.00")
    reference_number: str | None = None
    notes: str | None = None
    allocations: tuple[SupplierPaymentAllocationCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class PostSupplierPaymentCommand:
    actor_user_id: int | None = None
