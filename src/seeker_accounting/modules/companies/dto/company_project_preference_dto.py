from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ── Read DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CompanyProjectPreferenceDTO:
    company_id: int
    allow_projects_without_contract: bool
    default_budget_control_mode_code: str
    default_commitment_control_mode_code: str
    budget_warning_percent_threshold: float | None
    require_job_on_cost_posting: bool
    require_cost_code_on_cost_posting: bool
    updated_at: datetime
    updated_by_user_id: int | None


# ── Commands ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class UpdateCompanyProjectPreferencesCommand:
    allow_projects_without_contract: bool = field(default=True)
    default_budget_control_mode_code: str = field(default="")
    default_commitment_control_mode_code: str = field(default="")
    budget_warning_percent_threshold: float | None = field(default=None)
    require_job_on_cost_posting: bool = field(default=False)
    require_cost_code_on_cost_posting: bool = field(default=False)
    updated_by_user_id: int | None = field(default=None)