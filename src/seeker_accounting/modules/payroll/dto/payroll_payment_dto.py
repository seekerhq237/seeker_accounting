from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


_ALLOWED_PAYMENT_METHODS = frozenset(
    {"manual_bank", "cash", "cheque", "transfer_note", "other"}
)


@dataclass(frozen=True, slots=True)
class PayrollPaymentRecordDTO:
    id: int
    company_id: int
    run_employee_id: int
    payment_date: date
    amount_paid: Decimal
    payment_method_code: str | None
    payment_reference: str | None
    treasury_transaction_id: int | None
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CreatePayrollPaymentRecordCommand:
    run_employee_id: int
    payment_date: date
    amount_paid: Decimal
    payment_method_code: str | None = None
    payment_reference: str | None = None
    treasury_transaction_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdatePayrollPaymentRecordCommand:
    payment_date: date
    amount_paid: Decimal
    payment_method_code: str | None = None
    payment_reference: str | None = None
    treasury_transaction_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class EmployeePaymentSummaryDTO:
    run_employee_id: int
    run_id: int
    run_reference: str
    employee_id: int
    employee_number: str
    employee_display_name: str
    net_payable: Decimal
    total_paid: Decimal
    outstanding: Decimal
    payment_status_code: str
    payment_date: date | None
    records: tuple[PayrollPaymentRecordDTO, ...]
