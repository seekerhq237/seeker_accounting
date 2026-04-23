from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateProjectBudgetVersionCommand:
    company_id: int
    project_id: int
    version_number: int
    version_name: str
    version_type_code: str
    budget_date: date
    base_version_id: int | None = None
    revision_reason: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateProjectBudgetVersionCommand:
    version_name: str
    version_type_code: str
    budget_date: date
    base_version_id: int | None = None
    revision_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AddProjectBudgetLineCommand:
    project_budget_version_id: int
    line_number: int
    project_cost_code_id: int
    line_amount: Decimal
    project_job_id: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateProjectBudgetLineCommand:
    line_number: int
    project_cost_code_id: int
    line_amount: Decimal
    project_job_id: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class SubmitProjectBudgetVersionCommand:
    version_id: int
    company_id: int


@dataclass(frozen=True, slots=True)
class ApproveProjectBudgetVersionCommand:
    version_id: int
    company_id: int
    approved_by_user_id: int


@dataclass(frozen=True, slots=True)
class CancelProjectBudgetVersionCommand:
    version_id: int
    company_id: int


@dataclass(frozen=True, slots=True)
class CloneProjectBudgetVersionCommand:
    source_version_id: int
    company_id: int
    project_id: int
    version_name: str
    version_type_code: str
    budget_date: date
    revision_reason: str | None = None


@dataclass(frozen=True, slots=True)
class BudgetLineDraftDTO:
    """In-memory budget line payload used by the unified editor.

    Unlike ``AddProjectBudgetLineCommand`` this does not carry a version id —
    it is attached to whichever version the caller creates or replaces.
    """

    line_number: int
    project_cost_code_id: int
    line_amount: Decimal
    project_job_id: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CreateProjectBudgetVersionWithLinesCommand:
    """Atomic create: version header + every line in a single transaction."""

    company_id: int
    project_id: int
    version_number: int
    version_name: str
    version_type_code: str
    budget_date: date
    lines: tuple[BudgetLineDraftDTO, ...] = ()
    base_version_id: int | None = None
    revision_reason: str | None = None
