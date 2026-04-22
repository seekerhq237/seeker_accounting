from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class CreateProjectJobCommand:
    company_id: int
    project_id: int
    job_code: str
    job_name: str
    parent_job_id: int | None = None
    sequence_number: int = 0
    start_date: date | None = None
    planned_end_date: date | None = None
    allow_direct_cost_posting: bool = True
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateProjectJobCommand:
    job_name: str
    parent_job_id: int | None = None
    sequence_number: int = 0
    start_date: date | None = None
    planned_end_date: date | None = None
    allow_direct_cost_posting: bool = True
    notes: str | None = None
