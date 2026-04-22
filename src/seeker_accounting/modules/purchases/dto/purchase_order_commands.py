from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PurchaseOrderLineCommand:
    description: str
    quantity: Decimal
    unit_cost: Decimal
    discount_percent: Decimal | None = None
    discount_amount: Decimal | None = None
    tax_code_id: int | None = None
    expense_account_id: int | None = None
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreatePurchaseOrderCommand:
    supplier_id: int
    order_date: date
    expected_delivery_date: date | None = None
    currency_code: str = ""
    exchange_rate: Decimal | None = None
    reference_number: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[PurchaseOrderLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdatePurchaseOrderCommand:
    supplier_id: int
    order_date: date
    expected_delivery_date: date | None = None
    currency_code: str = ""
    exchange_rate: Decimal | None = None
    reference_number: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[PurchaseOrderLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class ConvertPurchaseOrderCommand:
    bill_date: date
    due_date: date
    reference_number: str | None = None
    notes: str | None = None
    actor_user_id: int | None = None
