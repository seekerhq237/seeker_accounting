from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CreateProjectCommitmentCommand:
    company_id: int
    project_id: int
    commitment_number: str
    commitment_type_code: str
    commitment_date: date
    currency_code: str
    supplier_id: int | None = None
    required_date: date | None = None
    exchange_rate: Decimal | None = None
    reference_number: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateProjectCommitmentCommand:
    commitment_type_code: str
    commitment_date: date
    currency_code: str
    supplier_id: int | None = None
    required_date: date | None = None
    exchange_rate: Decimal | None = None
    reference_number: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ApproveProjectCommitmentCommand:
    commitment_id: int
    company_id: int
    approved_by_user_id: int


@dataclass(frozen=True, slots=True)
class CloseProjectCommitmentCommand:
    commitment_id: int
    company_id: int


@dataclass(frozen=True, slots=True)
class CancelProjectCommitmentCommand:
    commitment_id: int
    company_id: int


@dataclass(frozen=True, slots=True)
class AddProjectCommitmentLineCommand:
    project_commitment_id: int
    line_number: int
    project_cost_code_id: int
    line_amount: Decimal
    project_job_id: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateProjectCommitmentLineCommand:
    line_number: int
    project_cost_code_id: int
    line_amount: Decimal
    project_job_id: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_rate: Decimal | None = None
    notes: str | None = None
