from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


# ── Compensation Profile DTOs ──────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class CompensationProfileListItemDTO:
    id: int
    company_id: int
    employee_id: int
    employee_number: str
    employee_display_name: str
    profile_name: str
    basic_salary: Decimal
    currency_code: str
    effective_from: date
    effective_to: date | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class CompensationProfileDetailDTO:
    id: int
    company_id: int
    employee_id: int
    employee_number: str
    employee_display_name: str
    profile_name: str
    basic_salary: Decimal
    currency_code: str
    effective_from: date
    effective_to: date | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CreateCompensationProfileCommand:
    employee_id: int
    profile_name: str
    basic_salary: Decimal
    currency_code: str
    effective_from: date
    effective_to: date | None = field(default=None)
    notes: str | None = field(default=None)


@dataclass(frozen=True, slots=True)
class UpdateCompensationProfileCommand:
    profile_name: str
    basic_salary: Decimal
    currency_code: str
    effective_from: date
    is_active: bool
    effective_to: date | None = field(default=None)
    notes: str | None = field(default=None)


# ── Component Assignment DTOs ──────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ComponentAssignmentListItemDTO:
    id: int
    company_id: int
    employee_id: int
    employee_display_name: str
    component_id: int
    component_code: str
    component_name: str
    component_type_code: str
    calculation_method_code: str
    override_amount: Decimal | None
    override_rate: Decimal | None
    effective_from: date
    effective_to: date | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class CreateComponentAssignmentCommand:
    employee_id: int
    component_id: int
    effective_from: date
    override_amount: Decimal | None = field(default=None)
    override_rate: Decimal | None = field(default=None)
    effective_to: date | None = field(default=None)


@dataclass(frozen=True, slots=True)
class UpdateComponentAssignmentCommand:
    component_id: int
    effective_from: date
    is_active: bool
    override_amount: Decimal | None = field(default=None)
    override_rate: Decimal | None = field(default=None)
    effective_to: date | None = field(default=None)


# ── Payroll Input DTOs ─────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PayrollInputBatchListItemDTO:
    id: int
    company_id: int
    batch_reference: str
    period_year: int
    period_month: int
    status_code: str
    description: str | None
    line_count: int


@dataclass(frozen=True, slots=True)
class PayrollInputBatchDetailDTO:
    id: int
    company_id: int
    batch_reference: str
    period_year: int
    period_month: int
    status_code: str
    description: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    lines: list[PayrollInputLineDTO]


@dataclass(frozen=True, slots=True)
class PayrollInputLineDTO:
    id: int
    batch_id: int
    employee_id: int
    employee_display_name: str
    component_id: int
    component_name: str
    component_type_code: str
    input_amount: Decimal
    input_quantity: Decimal | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class CreatePayrollInputBatchCommand:
    period_year: int
    period_month: int
    description: str | None = field(default=None)


@dataclass(frozen=True, slots=True)
class CreatePayrollInputLineCommand:
    employee_id: int
    component_id: int
    input_amount: Decimal
    input_quantity: Decimal | None = field(default=None)
    notes: str | None = field(default=None)


@dataclass(frozen=True, slots=True)
class UpdatePayrollInputLineCommand:
    input_amount: Decimal
    input_quantity: Decimal | None = field(default=None)
    notes: str | None = field(default=None)


# ── Payroll Run DTOs ───────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PayrollRunListItemDTO:
    id: int
    company_id: int
    run_reference: str
    run_label: str
    period_year: int
    period_month: int
    status_code: str
    currency_code: str
    run_date: date
    payment_date: date | None
    employee_count: int
    total_net_payable: Decimal
    total_gross_earnings: Decimal = field(default=Decimal("0"))
    posted_journal_entry_id: int | None = field(default=None)


@dataclass(frozen=True, slots=True)
class PayrollRunDetailDTO:
    id: int
    company_id: int
    run_reference: str
    run_label: str
    period_year: int
    period_month: int
    status_code: str
    currency_code: str
    run_date: date
    payment_date: date | None
    notes: str | None
    calculated_at: datetime | None
    approved_at: datetime | None
    posted_at: datetime | None = field(default=None)
    posted_by_user_id: int | None = field(default=None)
    posted_journal_entry_id: int | None = field(default=None)


@dataclass(frozen=True, slots=True)
class CreatePayrollRunCommand:
    period_year: int
    period_month: int
    run_label: str
    currency_code: str
    run_date: date
    payment_date: date | None = field(default=None)
    notes: str | None = field(default=None)


# ── Run Employee / Payslip DTOs ────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PayrollRunEmployeeListItemDTO:
    id: int
    run_id: int
    employee_id: int
    employee_number: str
    employee_display_name: str
    gross_earnings: Decimal
    total_employee_deductions: Decimal
    total_taxes: Decimal
    net_payable: Decimal
    employer_cost_base: Decimal
    status_code: str


@dataclass(frozen=True, slots=True)
class PayrollRunLineDTO:
    id: int
    component_id: int
    component_name: str
    component_code: str
    component_type_code: str
    calculation_basis: Decimal
    rate_applied: Decimal | None
    component_amount: Decimal


@dataclass(frozen=True, slots=True)
class PayrollRunEmployeeDetailDTO:
    id: int
    run_id: int
    run_reference: str
    period_year: int
    period_month: int
    employee_id: int
    employee_number: str
    employee_display_name: str

    # Six bases
    gross_earnings: Decimal
    taxable_salary_base: Decimal
    tdl_base: Decimal
    cnps_contributory_base: Decimal
    employer_cost_base: Decimal
    net_payable: Decimal

    # Summary totals
    total_earnings: Decimal
    total_employee_deductions: Decimal
    total_employer_contributions: Decimal
    total_taxes: Decimal

    status_code: str
    calculation_notes: str | None
    lines: list[PayrollRunLineDTO]


# ── Validation DTOs ────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PayrollValidationIssueDTO:
    employee_id: int
    employee_display_name: str
    issue_code: str
    issue_message: str
    severity: str  # error, warning


@dataclass(frozen=True, slots=True)
class PayrollValidationResultDTO:
    company_id: int
    period_year: int
    period_month: int
    employee_count: int
    issues: list[PayrollValidationIssueDTO]

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")
