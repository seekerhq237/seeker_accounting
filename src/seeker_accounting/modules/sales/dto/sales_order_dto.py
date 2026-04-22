from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SalesOrderLineDTO:
    id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal | None
    discount_amount: Decimal | None
    tax_code_id: int | None
    tax_code_name: str | None
    revenue_account_id: int | None
    revenue_account_code: str | None
    line_subtotal_amount: Decimal
    line_tax_amount: Decimal
    line_total_amount: Decimal
    contract_id: int | None
    project_id: int | None
    project_job_id: int | None
    project_cost_code_id: int | None


@dataclass(frozen=True, slots=True)
class SalesOrderTotalsDTO:
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_count: int


@dataclass(frozen=True, slots=True)
class SalesOrderListItemDTO:
    id: int
    order_number: str
    order_date: date
    requested_delivery_date: date | None
    customer_id: int
    customer_name: str
    currency_code: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status_code: str
    source_quote_id: int | None
    converted_to_invoice_id: int | None


@dataclass(frozen=True, slots=True)
class SalesOrderDetailDTO:
    id: int
    order_number: str
    order_date: date
    requested_delivery_date: date | None
    customer_id: int
    customer_name: str
    currency_code: str
    exchange_rate: Decimal | None
    status_code: str
    reference_number: str | None
    notes: str | None
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    contract_id: int | None
    project_id: int | None
    source_quote_id: int | None
    converted_to_invoice_id: int | None
    lines: tuple[SalesOrderLineDTO, ...]


@dataclass(frozen=True, slots=True)
class SalesOrderConversionResultDTO:
    order_id: int
    order_number: str
    invoice_id: int
