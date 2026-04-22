from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PayrollProjectAllocationLineCommand:
    project_id: int
    allocation_basis_code: str
    contract_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None
    allocation_quantity: Decimal | None = None
    allocation_percent: Decimal | None = None
    allocated_cost_amount: Decimal | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ReplacePayrollProjectAllocationsCommand:
    lines: tuple[PayrollProjectAllocationLineCommand, ...] = field(default_factory=tuple)