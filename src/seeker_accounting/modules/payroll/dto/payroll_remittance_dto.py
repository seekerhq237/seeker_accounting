from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


_ALLOWED_AUTHORITIES = frozenset({"dgi", "cnps", "other"})
_ALLOWED_BATCH_STATUSES = frozenset({"draft", "open", "partial", "paid", "cancelled"})
_ALLOWED_LINE_STATUSES = frozenset({"open", "partial", "paid", "cancelled"})


@dataclass(frozen=True, slots=True)
class PayrollRemittanceLineDTO:
    id: int
    payroll_remittance_batch_id: int
    line_number: int
    payroll_component_id: int | None
    payroll_component_name: str | None
    liability_account_id: int | None
    liability_account_code: str | None
    description: str
    amount_due: Decimal
    amount_paid: Decimal
    outstanding: Decimal
    status_code: str
    notes: str | None


@dataclass(frozen=True, slots=True)
class PayrollRemittanceBatchListItemDTO:
    id: int
    company_id: int
    batch_number: str
    payroll_run_id: int | None
    payroll_run_reference: str | None
    period_start_date: date
    period_end_date: date
    remittance_authority_code: str
    remittance_date: date | None
    amount_due: Decimal
    amount_paid: Decimal
    outstanding: Decimal
    status_code: str


@dataclass(frozen=True, slots=True)
class PayrollRemittanceBatchDetailDTO:
    id: int
    company_id: int
    batch_number: str
    payroll_run_id: int | None
    payroll_run_reference: str | None
    period_start_date: date
    period_end_date: date
    remittance_authority_code: str
    remittance_date: date | None
    amount_due: Decimal
    amount_paid: Decimal
    outstanding: Decimal
    status_code: str
    reference: str | None
    treasury_transaction_id: int | None
    notes: str | None
    lines: tuple[PayrollRemittanceLineDTO, ...]


@dataclass(frozen=True, slots=True)
class CreatePayrollRemittanceBatchCommand:
    period_start_date: date
    period_end_date: date
    remittance_authority_code: str
    payroll_run_id: int | None = None
    amount_due: Decimal = Decimal("0")
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdatePayrollRemittanceBatchCommand:
    remittance_date: date | None
    amount_due: Decimal
    reference: str | None = None
    treasury_transaction_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CreatePayrollRemittanceLineCommand:
    description: str
    amount_due: Decimal
    payroll_component_id: int | None = None
    liability_account_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdatePayrollRemittanceLineCommand:
    description: str
    amount_due: Decimal
    amount_paid: Decimal
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class RecordRemittancePaymentCommand:
    amount_paid: Decimal
    remittance_date: date
    reference: str | None = None
    treasury_transaction_id: int | None = None


@dataclass(frozen=True, slots=True)
class RemittanceLineReconciliationDTO:
    """Per-line comparison of a remittance line against posted GL liability.

    ``gl_liability_balance`` is the credit-minus-debit balance of the
    associated liability account, restricted to journal entries posted in
    the batch's period. A positive value means GL still owes that amount.
    ``variance = amount_due - gl_liability_balance``: zero (within
    tolerance) means the remittance line matches what the books say is
    owed.
    """
    line_id: int
    line_number: int
    description: str
    payroll_component_id: int | None
    liability_account_id: int | None
    liability_account_code: str | None
    amount_due: Decimal
    amount_paid: Decimal
    gl_liability_balance: Decimal
    variance: Decimal
    is_reconciled: bool


@dataclass(frozen=True, slots=True)
class RemittanceBatchReconciliationDTO:
    batch_id: int
    batch_number: str
    period_start_date: date
    period_end_date: date
    remittance_authority_code: str
    total_amount_due: Decimal
    total_gl_liability_balance: Decimal
    total_variance: Decimal
    is_fully_reconciled: bool
    lines_without_account: tuple[int, ...]
    lines: tuple[RemittanceLineReconciliationDTO, ...]
