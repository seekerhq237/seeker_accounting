from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ProjectJobListItemDTO:
    id: int
    project_id: int
    job_code: str
    job_name: str
    parent_job_id: int | None
    parent_job_code: str | None
    sequence_number: int
    status_code: str
    start_date: date | None
    planned_end_date: date | None
    allow_direct_cost_posting: bool
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProjectJobDetailDTO:
    id: int
    company_id: int
    project_id: int
    job_code: str
    job_name: str
    parent_job_id: int | None
    parent_job_code: str | None
    sequence_number: int
    status_code: str
    start_date: date | None
    planned_end_date: date | None
    actual_end_date: date | None
    allow_direct_cost_posting: bool
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None
