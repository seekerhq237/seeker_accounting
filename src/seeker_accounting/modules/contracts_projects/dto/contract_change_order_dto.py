from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


# ── Read DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ContractChangeOrderListItemDTO:
    id: int
    change_order_number: str
    change_order_date: date
    status_code: str
    change_type_code: str
    description: str | None
    contract_amount_delta: Decimal | None
    days_extension: int | None
    effective_date: date | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ContractChangeOrderDetailDTO:
    id: int
    company_id: int
    contract_id: int
    change_order_number: str
    change_order_date: date
    status_code: str
    change_type_code: str
    description: str | None
    contract_amount_delta: Decimal | None
    days_extension: int | None
    effective_date: date | None
    approved_at: datetime | None
    approved_by_user_id: int | None
    approved_by_display_name: str | None
    created_at: datetime
    updated_at: datetime
