from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateContractChangeOrderCommand:
    company_id: int
    contract_id: int
    change_order_number: str
    change_order_date: date
    change_type_code: str
    description: str | None = None
    contract_amount_delta: Decimal | None = None
    days_extension: int | None = None
    effective_date: date | None = None


@dataclass(frozen=True, slots=True)
class UpdateContractChangeOrderCommand:
    change_order_date: date
    change_type_code: str
    description: str | None = None
    contract_amount_delta: Decimal | None = None
    days_extension: int | None = None
    effective_date: date | None = None


@dataclass(frozen=True, slots=True)
class SubmitContractChangeOrderCommand:
    change_order_id: int


@dataclass(frozen=True, slots=True)
class ApproveContractChangeOrderCommand:
    change_order_id: int
    approved_by_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class RejectContractChangeOrderCommand:
    change_order_id: int
