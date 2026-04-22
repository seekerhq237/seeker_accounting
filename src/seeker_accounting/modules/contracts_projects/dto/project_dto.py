from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


# ── Read DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProjectListItemDTO:
    id: int
    project_code: str
    project_name: str
    contract_number: str | None
    customer_display_name: str | None
    project_type_code: str
    status_code: str
    start_date: datetime | None
    planned_end_date: datetime | None
    project_manager_display_name: str | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectDetailDTO:
    id: int
    company_id: int
    project_code: str
    project_name: str
    contract_id: int | None
    contract_number: str | None
    customer_id: int | None
    customer_display_name: str | None
    project_type_code: str
    project_manager_user_id: int | None
    project_manager_display_name: str | None
    currency_code: str | None
    exchange_rate: Decimal | None
    start_date: datetime | None
    planned_end_date: datetime | None
    actual_end_date: datetime | None
    status_code: str
    budget_control_mode_code: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None


# ── Commands ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CreateProjectCommand:
    company_id: int
    project_code: str
    project_name: str
    contract_id: int | None = None
    customer_id: int | None = None
    project_type_code: str = "external"
    project_manager_user_id: int | None = None
    currency_code: str | None = None
    exchange_rate: Decimal | None = None
    start_date: datetime | None = None
    planned_end_date: datetime | None = None
    budget_control_mode_code: str | None = None
    notes: str | None = None
    created_by_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class UpdateProjectCommand:
    project_name: str
    contract_id: int | None = None
    customer_id: int | None = None
    project_type_code: str = "external"
    project_manager_user_id: int | None = None
    currency_code: str | None = None
    exchange_rate: Decimal | None = None
    start_date: datetime | None = None
    planned_end_date: datetime | None = None
    budget_control_mode_code: str | None = None
    notes: str | None = None
    updated_by_user_id: int | None = None