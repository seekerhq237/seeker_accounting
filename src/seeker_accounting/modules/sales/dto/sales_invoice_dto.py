from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SalesInvoiceListItemDTO:
    id: int
    company_id: int
    invoice_number: str
    customer_id: int
    customer_code: str
    customer_name: str
    invoice_date: date
    due_date: date
    currency_code: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    allocated_amount: Decimal
    open_balance_amount: Decimal
    status_code: str
    payment_status_code: str
    posted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SalesInvoiceLineDTO:
    id: int
    sales_invoice_id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal | None
    discount_amount: Decimal | None
    tax_code_id: int | None
    tax_code_code: str | None
    tax_code_name: str | None
    revenue_account_id: int
    revenue_account_code: str
    revenue_account_name: str
    line_subtotal_amount: Decimal
    line_tax_amount: Decimal
    line_total_amount: Decimal
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class SalesInvoiceTotalsDTO:
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    allocated_amount: Decimal
    open_balance_amount: Decimal


@dataclass(frozen=True, slots=True)
class SalesInvoiceDetailDTO:
    id: int
    company_id: int
    invoice_number: str
    customer_id: int
    customer_code: str
    customer_name: str
    invoice_date: date
    due_date: date
    currency_code: str
    exchange_rate: Decimal | None
    status_code: str
    payment_status_code: str
    reference_number: str | None
    notes: str | None
    posted_journal_entry_id: int | None
    posted_at: datetime | None
    posted_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    totals: SalesInvoiceTotalsDTO
    lines: tuple[SalesInvoiceLineDTO, ...]
    contract_id: int | None = None
    project_id: int | None = None


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
class SalesPostingResultDTO:
    company_id: int
    sales_invoice_id: int
    invoice_number: str
    journal_entry_id: int
    journal_entry_number: str
    posted_at: datetime
    posted_by_user_id: int | None
    payment_status_code: str
    open_balance_amount: Decimal

