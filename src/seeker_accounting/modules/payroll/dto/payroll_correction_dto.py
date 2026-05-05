from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class EmployeePayrollCorrectionDTO:
    id: int
    company_id: int
    employee_id: int
    employee_display_name: str
    component_id: int
    component_code: str
    component_name: str
    component_type_code: str
    period_year: int
    period_month: int
    correction_amount: Decimal
    reason_code: str
    description: str | None
    status_code: str
    source_run_id: int | None
    applied_run_id: int | None
    applied_run_employee_id: int | None
    applied_at: datetime | None
    created_by_user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ApplyPayrollCorrectionCommand:
    employee_id: int
    component_id: int
    period_year: int
    period_month: int
    correction_amount: Decimal
    reason_code: str
    description: str | None = field(default=None)
    source_run_id: int | None = field(default=None)
    created_by_user_id: int | None = field(default=None)
