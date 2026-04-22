from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CustomerQuoteListItemDTO:
    id: int
    company_id: int
    quote_number: str
    customer_id: int
    customer_code: str
    customer_name: str
    quote_date: date
    expiry_date: date | None
    currency_code: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status_code: str
    converted_to_invoice_id: int | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerQuoteLineDTO:
    id: int
    customer_quote_id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal | None
    discount_amount: Decimal | None
    tax_code_id: int | None
    tax_code_code: str | None
    tax_code_name: str | None
    revenue_account_id: int | None
    revenue_account_code: str | None
    revenue_account_name: str | None
    line_subtotal_amount: Decimal
    line_tax_amount: Decimal
    line_total_amount: Decimal
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class CustomerQuoteTotalsDTO:
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class CustomerQuoteDetailDTO:
    id: int
    company_id: int
    quote_number: str
    customer_id: int
    customer_code: str
    customer_name: str
    quote_date: date
    expiry_date: date | None
    currency_code: str
    exchange_rate: Decimal | None
    status_code: str
    reference_number: str | None
    notes: str | None
    converted_to_invoice_id: int | None
    created_at: datetime
    updated_at: datetime
    totals: CustomerQuoteTotalsDTO
    lines: tuple[CustomerQuoteLineDTO, ...]
    contract_id: int | None = None
    project_id: int | None = None


@dataclass(frozen=True, slots=True)
class CustomerQuoteConversionResultDTO:
    quote_id: int
    quote_number: str
    sales_invoice_id: int
    invoice_number: str
