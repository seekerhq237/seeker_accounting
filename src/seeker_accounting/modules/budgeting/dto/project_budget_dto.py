from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProjectBudgetVersionListItemDTO:
    id: int
    project_id: int
    version_number: int
    version_name: str
    version_type_code: str
    status_code: str
    budget_date: date
    total_budget_amount: Decimal
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProjectBudgetVersionDetailDTO:
    id: int
    company_id: int
    project_id: int
    version_number: int
    version_name: str
    version_type_code: str
    status_code: str
    base_version_id: int | None
    base_version_name: str | None
    budget_date: date
    revision_reason: str | None
    total_budget_amount: Decimal
    approved_at: datetime | None
    approved_by_user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProjectBudgetLineDTO:
    id: int
    project_budget_version_id: int
    line_number: int
    project_job_id: int | None
    project_job_code: str | None
    project_cost_code_id: int
    project_cost_code_name: str | None
    description: str | None
    quantity: Decimal | None
    unit_rate: Decimal | None
    line_amount: Decimal
    start_date: date | None
    end_date: date | None
    notes: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CurrentApprovedBudgetDTO:
    project_id: int
    version_id: int
    version_number: int
    version_name: str
    total_budget_amount: Decimal
    budget_date: date
    approved_at: datetime | None
