from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ContractLineCommand:
    description: str
    quantity: Decimal
    unit_rate: Decimal
    tax_code_id: int | None = None
    tax_treatment_code: str | None = None
    billing_basis_code: str = "milestone"
    project_id: int | None = None
    project_job_id: int | None = None
    change_order_id: int | None = None
    line_amount: Decimal | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ContractBillingScheduleItemCommand:
    schedule_type_code: str
    description: str
    scheduled_amount: Decimal
    scheduled_date: date | None = None
    milestone_code: str | None = None
    billing_percent: Decimal | None = None
    retention_percent: Decimal | None = None
    advance_recovery_percent: Decimal | None = None
    time_material_reference: str | None = None
    contract_line_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    status_code: str = "planned"
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ContractLineDTO:
    id: int
    company_id: int
    contract_id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_rate: Decimal
    line_amount: Decimal
    tax_code_id: int | None
    tax_treatment_code: str | None
    billing_basis_code: str
    project_id: int | None
    project_job_id: int | None
    change_order_id: int | None
    status_code: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class ContractBillingScheduleItemDTO:
    id: int
    company_id: int
    contract_id: int
    line_number: int
    schedule_type_code: str
    description: str
    scheduled_amount: Decimal
    scheduled_date: date | None
    milestone_code: str | None
    billing_percent: Decimal | None
    retention_percent: Decimal | None
    advance_recovery_percent: Decimal | None
    time_material_reference: str | None
    contract_line_id: int | None
    project_id: int | None
    project_job_id: int | None
    status_code: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class ContractCommercialSummaryDTO:
    company_id: int
    contract_id: int
    original_contract_value: Decimal
    approved_variations: Decimal
    current_contract_value: Decimal
    billing_schedule_total: Decimal
    billing_schedule_variance: Decimal
    billed_amount: Decimal
    certified_amount: Decimal
    earned_amount: Decimal
    collected_amount: Decimal
    unrecovered_advance_amount: Decimal
    open_retention_amount: Decimal
    schedule_reconciles_to_contract_value: bool
