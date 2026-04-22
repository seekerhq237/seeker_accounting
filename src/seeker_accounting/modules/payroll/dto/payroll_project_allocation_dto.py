from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PayrollProjectAllocationLineDTO:
    id: int
    line_number: int
    contract_id: int | None
    contract_number: str | None
    project_id: int
    project_code: str
    project_name: str
    project_job_id: int | None
    project_job_code: str | None
    project_job_name: str | None
    project_cost_code_id: int | None
    project_cost_code_code: str | None
    project_cost_code_name: str | None
    allocation_basis_code: str
    allocation_quantity: Decimal | None
    allocation_percent: Decimal | None
    allocated_cost_amount: Decimal
    notes: str | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class PayrollProjectAllocationSetDTO:
    payroll_run_employee_id: int
    run_id: int
    run_reference: str
    run_status_code: str
    employee_id: int
    employee_number: str
    employee_display_name: str
    employee_status_code: str
    allocation_base_code: str
    allocation_base_amount: Decimal
    total_allocated_amount: Decimal
    remaining_unallocated_amount: Decimal
    editable: bool
    lines: tuple[PayrollProjectAllocationLineDTO, ...] = field(default_factory=tuple)