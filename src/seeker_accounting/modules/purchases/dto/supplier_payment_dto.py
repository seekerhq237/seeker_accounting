from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SupplierPaymentListItemDTO:
    id: int
    company_id: int
    payment_number: str
    supplier_id: int
    supplier_code: str
    supplier_name: str
    financial_account_id: int
    financial_account_code: str
    financial_account_name: str
    payment_date: date
    currency_code: str
    amount_paid: Decimal
    status_code: str
    posted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SupplierPaymentAllocationDTO:
    id: int
    company_id: int
    supplier_payment_id: int
    purchase_bill_id: int
    purchase_bill_number: str
    purchase_bill_date: date
    purchase_bill_due_date: date
    bill_currency_code: str
    bill_total_amount: Decimal
    allocated_amount: Decimal
    allocation_date: date
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SupplierPaymentDetailDTO:
    id: int
    company_id: int
    payment_number: str
    supplier_id: int
    supplier_code: str
    supplier_name: str
    financial_account_id: int
    financial_account_code: str
    financial_account_name: str
    payment_date: date
    currency_code: str
    exchange_rate: Decimal | None
    amount_paid: Decimal
    status_code: str
    reference_number: str | None
    notes: str | None
    posted_journal_entry_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    allocated_amount: Decimal
    remaining_unallocated_amount: Decimal
    allocations: tuple[SupplierPaymentAllocationDTO, ...]


@dataclass(frozen=True, slots=True)
class PaymentPostingResultDTO:
    company_id: int
    supplier_payment_id: int
    payment_number: str
    journal_entry_id: int
    journal_entry_number: str
    posted_at: datetime
    posted_by_user_id: int | None
    allocated_amount: Decimal
    remaining_unallocated_amount: Decimal


@dataclass(frozen=True, slots=True)
class BillPaymentRowDTO:
    """A payment that has been (partially or fully) allocated to a specific bill."""
    payment_id: int
    payment_number: str
    payment_date: date
    financial_account_code: str
    financial_account_name: str
    currency_code: str
    amount_paid: Decimal
    allocated_to_bill: Decimal
    status_code: str
