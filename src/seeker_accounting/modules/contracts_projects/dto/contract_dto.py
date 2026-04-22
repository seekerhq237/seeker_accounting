from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


# ── Read DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ContractListItemDTO:
    id: int
    contract_number: str
    contract_title: str
    customer_display_name: str
    contract_type_code: str
    status_code: str
    start_date: datetime | None
    planned_end_date: datetime | None
    base_contract_amount: Decimal | None
    currency_code: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ContractDetailDTO:
    id: int
    company_id: int
    contract_number: str
    contract_title: str
    customer_id: int
    customer_display_name: str
    contract_type_code: str
    currency_code: str
    exchange_rate: Decimal | None
    base_contract_amount: Decimal | None
    start_date: datetime | None
    planned_end_date: datetime | None
    actual_end_date: datetime | None
    status_code: str
    billing_basis_code: str | None
    retention_percent: Decimal | None
    reference_number: str | None
    description: str | None
    approved_at: datetime | None
    approved_by_user_id: int | None
    approved_by_display_name: str | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None
    approved_change_order_delta_total: Decimal
    current_contract_amount: Decimal | None


# ── Commands ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CreateContractCommand:
    company_id: int
    contract_number: str
    contract_title: str
    customer_id: int
    contract_type_code: str
    currency_code: str
    exchange_rate: Decimal | None = None
    base_contract_amount: Decimal | None = None
    start_date: datetime | None = None
    planned_end_date: datetime | None = None
    billing_basis_code: str | None = None
    retention_percent: Decimal | None = None
    reference_number: str | None = None
    description: str | None = None
    created_by_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class UpdateContractCommand:
    contract_title: str
    contract_type_code: str
    currency_code: str
    exchange_rate: Decimal | None = None
    base_contract_amount: Decimal | None = None
    start_date: datetime | None = None
    planned_end_date: datetime | None = None
    billing_basis_code: str | None = None
    retention_percent: Decimal | None = None
    reference_number: str | None = None
    description: str | None = None
    updated_by_user_id: int | None = None