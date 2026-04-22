from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PurchaseOrderListItemDTO:
    id: int
    company_id: int
    order_number: str
    supplier_id: int
    supplier_code: str
    supplier_name: str
    order_date: date
    expected_delivery_date: date | None
    currency_code: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status_code: str
    converted_to_bill_id: int | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PurchaseOrderLineDTO:
    id: int
    purchase_order_id: int
    line_number: int
    description: str
    quantity: Decimal
    unit_cost: Decimal
    discount_percent: Decimal | None
    discount_amount: Decimal | None
    tax_code_id: int | None
    tax_code_code: str | None
    tax_code_name: str | None
    expense_account_id: int | None
    expense_account_code: str | None
    expense_account_name: str | None
    line_subtotal_amount: Decimal
    line_tax_amount: Decimal
    line_total_amount: Decimal
    contract_id: int | None = None
    project_id: int | None = None
    project_job_id: int | None = None
    project_cost_code_id: int | None = None


@dataclass(frozen=True, slots=True)
class PurchaseOrderTotalsDTO:
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


@dataclass(frozen=True, slots=True)
class PurchaseOrderDetailDTO:
    id: int
    company_id: int
    order_number: str
    supplier_id: int
    supplier_code: str
    supplier_name: str
    order_date: date
    expected_delivery_date: date | None
    currency_code: str
    exchange_rate: Decimal | None
    status_code: str
    reference_number: str | None
    notes: str | None
    converted_to_bill_id: int | None
    created_at: datetime
    updated_at: datetime
    totals: PurchaseOrderTotalsDTO
    lines: tuple[PurchaseOrderLineDTO, ...]
    contract_id: int | None = None
    project_id: int | None = None


@dataclass(frozen=True, slots=True)
class PurchaseOrderConversionResultDTO:
    order_id: int
    order_number: str
    purchase_bill_id: int
    bill_number: str
