from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CustomerReceiptListItemDTO:
    id: int
    company_id: int
    receipt_number: str
    customer_id: int
    customer_code: str
    customer_name: str
    financial_account_id: int
    financial_account_code: str
    financial_account_name: str
    receipt_date: date
    currency_code: str
    amount_received: Decimal
    status_code: str
    posted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerReceiptAllocationDTO:
    id: int
    company_id: int
    customer_receipt_id: int
    sales_invoice_id: int
    sales_invoice_number: str
    sales_invoice_date: date
    sales_invoice_due_date: date
    invoice_currency_code: str
    invoice_total_amount: Decimal
    allocated_amount: Decimal
    allocation_date: date
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerOpenInvoiceDTO:
    id: int
    invoice_number: str
    invoice_date: date
    due_date: date
    currency_code: str
    total_amount: Decimal
    allocated_amount: Decimal
    open_balance_amount: Decimal
    payment_status_code: str


@dataclass(frozen=True, slots=True)
class CustomerReceiptDetailDTO:
    id: int
    company_id: int
    receipt_number: str
    customer_id: int
    customer_code: str
    customer_name: str
    financial_account_id: int
    financial_account_code: str
    financial_account_name: str
    receipt_date: date
    currency_code: str
    exchange_rate: Decimal | None
    amount_received: Decimal
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
    allocations: tuple[CustomerReceiptAllocationDTO, ...]


@dataclass(frozen=True, slots=True)
class ReceiptPostingResultDTO:
    company_id: int
    customer_receipt_id: int
    receipt_number: str
    journal_entry_id: int
    journal_entry_number: str
    posted_at: datetime
    posted_by_user_id: int | None
    allocated_amount: Decimal
    remaining_unallocated_amount: Decimal


@dataclass(frozen=True, slots=True)
class InvoiceReceiptRowDTO:
    """A receipt that has been (partially or fully) allocated to a specific invoice."""
    receipt_id: int
    receipt_number: str
    receipt_date: date
    financial_account_code: str
    financial_account_name: str
    currency_code: str
    amount_received: Decimal
    allocated_to_invoice: Decimal
    status_code: str

