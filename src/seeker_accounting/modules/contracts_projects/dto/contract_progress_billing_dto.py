from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProgressClaimLineCommand:
    description: str
    quantity: Decimal
    unit_rate: Decimal
    claimed_amount: Decimal | None = None
    certified_amount: Decimal | None = None
    contract_line_id: int | None = None
    billing_schedule_item_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CreateProgressClaimCommand:
    contract_id: int
    claim_number: str
    claim_date: date
    certified_amount: Decimal
    previous_certified_amount: Decimal | None = None
    current_claim_amount: Decimal | None = None
    earned_amount: Decimal | None = None
    taxable_base_amount: Decimal | None = None
    vat_amount: Decimal = Decimal("0.00")
    retention_percent: Decimal | None = None
    retention_amount: Decimal | None = None
    advance_recovery_amount: Decimal = Decimal("0.00")
    withheld_vat_amount: Decimal = Decimal("0.00")
    withholding_tax_amount: Decimal = Decimal("0.00")
    billing_schedule_item_id: int | None = None
    source_reference: str | None = None
    notes: str | None = None
    lines: tuple[ProgressClaimLineCommand, ...] = ()


@dataclass(frozen=True, slots=True)
class GenerateProgressInvoiceCommand:
    claim_id: int
    invoice_date: date
    due_date: date
    revenue_account_id: int
    tax_code_id: int | None = None
    actor_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class RecordCustomerAdvanceCommand:
    contract_id: int
    advance_number: str
    advance_date: date
    advance_amount: Decimal
    received_amount: Decimal
    source_invoice_id: int | None = None
    customer_receipt_id: int | None = None
    recovery_basis_code: str | None = None
    recovery_percent: Decimal | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class RecordContractReceiptAllocationCommand:
    contract_id: int
    allocation_date: date
    gross_amount: Decimal
    net_receivable_amount: Decimal
    withholding_vat_amount: Decimal = Decimal("0.00")
    withholding_tax_amount: Decimal = Decimal("0.00")
    retention_amount: Decimal = Decimal("0.00")
    advance_recovery_amount: Decimal = Decimal("0.00")
    customer_receipt_id: int | None = None
    sales_invoice_id: int | None = None
    progress_claim_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseRetentionCommand:
    contract_id: int
    movement_date: date
    amount: Decimal
    movement_type_code: str = "partial_release"
    customer_receipt_id: int | None = None
    sales_invoice_id: int | None = None
    progress_claim_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ProgressClaimLineDTO:
    id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_rate: Decimal
    claimed_amount: Decimal
    certified_amount: Decimal
    contract_line_id: int | None
    billing_schedule_item_id: int | None
    project_id: int | None
    project_job_id: int | None
    project_cost_code_id: int | None


@dataclass(frozen=True, slots=True)
class ProgressClaimDTO:
    id: int
    company_id: int
    contract_id: int
    claim_number: str
    claim_date: date
    status_code: str
    billing_schedule_item_id: int | None
    sales_invoice_id: int | None
    taxable_base_amount: Decimal
    previous_certified_amount: Decimal
    current_claim_amount: Decimal
    certified_amount: Decimal
    earned_amount: Decimal
    vat_amount: Decimal
    retention_percent: Decimal | None
    retention_amount: Decimal
    advance_recovery_amount: Decimal
    withheld_vat_amount: Decimal
    withholding_tax_amount: Decimal
    net_receivable_amount: Decimal
    source_reference: str | None
    notes: str | None
    certified_at: datetime | None
    certified_by_user_id: int | None
    lines: tuple[ProgressClaimLineDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class ContractAdvanceBalanceDTO:
    company_id: int
    contract_id: int
    received_advance_amount: Decimal
    recovered_advance_amount: Decimal
    unrecovered_advance_amount: Decimal


@dataclass(frozen=True, slots=True)
class ContractRetentionBalanceDTO:
    company_id: int
    contract_id: int
    open_retention_amount: Decimal


@dataclass(frozen=True, slots=True)
class ProgressInvoiceResultDTO:
    progress_claim_id: int
    sales_invoice_id: int
    invoice_number: str
    gross_claim_amount: Decimal
    vat_amount: Decimal
    retention_amount: Decimal
    advance_recovery_amount: Decimal
    withheld_vat_amount: Decimal
    withholding_tax_amount: Decimal
    net_receivable_amount: Decimal


@dataclass(frozen=True, slots=True)
class CustomerAdvanceDTO:
    id: int
    company_id: int
    contract_id: int
    advance_number: str
    advance_date: date
    status_code: str
    advance_amount: Decimal
    received_amount: Decimal
    recovery_basis_code: str | None
    recovery_percent: Decimal | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class RetentionMovementDTO:
    id: int
    company_id: int
    contract_id: int
    movement_date: date
    due_date: date | None
    movement_type_code: str
    status_code: str
    amount: Decimal
    progress_claim_id: int | None
    sales_invoice_id: int | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class ReceiptAllocationDTO:
    id: int
    company_id: int
    contract_id: int
    allocation_date: date
    gross_amount: Decimal
    net_receivable_amount: Decimal
    withholding_vat_amount: Decimal
    withholding_tax_amount: Decimal
    retention_amount: Decimal
    advance_recovery_amount: Decimal
    total_allocated_amount: Decimal
    progress_claim_id: int | None
    sales_invoice_id: int | None
    notes: str | None
