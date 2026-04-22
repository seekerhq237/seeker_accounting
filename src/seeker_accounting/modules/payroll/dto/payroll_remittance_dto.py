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
