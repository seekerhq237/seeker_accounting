from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProjectCommitmentListItemDTO:
    id: int
    commitment_number: str
    project_id: int
    project_name: str
    commitment_type_code: str
    commitment_date: date
    currency_code: str
    status_code: str
    total_amount: Decimal
    supplier_name: str | None
    reference_number: str | None


@dataclass(frozen=True, slots=True)
class ProjectCommitmentLineDTO:
    id: int
    line_number: int
    project_cost_code_id: int
    cost_code_name: str
    line_amount: Decimal
    project_job_id: int | None
    job_name: str | None
    description: str | None
    quantity: Decimal | None
    unit_rate: Decimal | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class ProjectCommitmentDetailDTO:
    id: int
    commitment_number: str
    company_id: int
    project_id: int
    project_name: str
    commitment_type_code: str
    commitment_date: date
    currency_code: str
    status_code: str
    total_amount: Decimal
    supplier_id: int | None
    supplier_name: str | None
    required_date: date | None
    exchange_rate: Decimal | None
    reference_number: str | None
    notes: str | None
    approved_at: datetime | None
    approved_by_user_id: int | None
    lines: list[ProjectCommitmentLineDTO]
    created_at: datetime
    updated_at: datetime
