from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PurchaseBillLineCommand:
    description: str
    quantity: Decimal | None = None
    unit_cost: Decimal | None = None
    tax_code_id: int | None = None
    expense_account_id: int = 0
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreatePurchaseBillCommand:
    supplier_id: int
    bill_date: date
    due_date: date
    currency_code: str
    exchange_rate: Decimal | None = None
    supplier_bill_reference: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[PurchaseBillLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdatePurchaseBillCommand:
    supplier_id: int
    bill_date: date
    due_date: date
    currency_code: str
    exchange_rate: Decimal | None = None
    supplier_bill_reference: str | None = None
    notes: str | None = None
    contract_id: int | None = None
    project_id: int | None = None
    lines: tuple[PurchaseBillLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class PostPurchaseBillCommand:
    actor_user_id: int | None = None
