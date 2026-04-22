from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.sales.models.customer_receipt import CustomerReceipt
from seeker_accounting.modules.sales.models.customer_receipt_allocation import CustomerReceiptAllocation
from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice


class CustomerReceiptAllocationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_receipt(self, company_id: int, receipt_id: int) -> list[CustomerReceiptAllocation]:
        statement = (
            select(CustomerReceiptAllocation)
            .join(CustomerReceipt, CustomerReceipt.id == CustomerReceiptAllocation.customer_receipt_id)
            .where(
                CustomerReceiptAllocation.company_id == company_id,
                CustomerReceiptAllocation.customer_receipt_id == receipt_id,
            )
            .options(selectinload(CustomerReceiptAllocation.sales_invoice))
            .order_by(CustomerReceiptAllocation.id.asc())
        )
        return list(self._session.scalars(statement))

    def list_for_invoice(self, company_id: int, invoice_id: int) -> list[CustomerReceiptAllocation]:
        statement = (
            select(CustomerReceiptAllocation)
            .join(SalesInvoice, SalesInvoice.id == CustomerReceiptAllocation.sales_invoice_id)
            .where(
                CustomerReceiptAllocation.company_id == company_id,
                CustomerReceiptAllocation.sales_invoice_id == invoice_id,
            )
            .options(
                selectinload(CustomerReceiptAllocation.customer_receipt)
                .selectinload(CustomerReceipt.financial_account),
                selectinload(CustomerReceiptAllocation.sales_invoice),
            )
            .order_by(CustomerReceiptAllocation.allocation_date.asc(), CustomerReceiptAllocation.id.asc())
        )
        return list(self._session.scalars(statement))

    def get_total_allocated_for_receipt(self, company_id: int, receipt_id: int) -> Decimal:
        statement = (
            select(func.coalesce(func.sum(CustomerReceiptAllocation.allocated_amount), 0))
            .where(
                CustomerReceiptAllocation.company_id == company_id,
                CustomerReceiptAllocation.customer_receipt_id == receipt_id,
            )
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def get_allocated_totals_for_invoice_ids(
        self,
        company_id: int,
        invoice_ids: list[int] | tuple[int, ...],
        posted_only: bool = True,
    ) -> dict[int, Decimal]:
        if not invoice_ids:
            return {}

        statement = (
            select(
                CustomerReceiptAllocation.sales_invoice_id,
                func.coalesce(func.sum(CustomerReceiptAllocation.allocated_amount), 0),
            )
            .join(CustomerReceipt, CustomerReceipt.id == CustomerReceiptAllocation.customer_receipt_id)
            .where(
                CustomerReceiptAllocation.company_id == company_id,
                CustomerReceiptAllocation.sales_invoice_id.in_(invoice_ids),
            )
            .group_by(CustomerReceiptAllocation.sales_invoice_id)
        )
        if posted_only:
            statement = statement.where(CustomerReceipt.status_code == "posted")

        results: dict[int, Decimal] = {}
        for invoice_id, amount in self._session.execute(statement):
            results[int(invoice_id)] = Decimal(str(amount or 0)).quantize(Decimal("0.00"))
        return results

    def replace_allocations_for_receipt(
        self,
        company_id: int,
        receipt_id: int,
        allocations: list[CustomerReceiptAllocation],
    ) -> list[CustomerReceiptAllocation]:
        for existing_allocation in self.list_for_receipt(company_id, receipt_id):
            self._session.delete(existing_allocation)
        self._session.flush()
        for allocation in allocations:
            allocation.customer_receipt_id = receipt_id
            self._session.add(allocation)
        return allocations

    def add(self, allocation: CustomerReceiptAllocation) -> CustomerReceiptAllocation:
        self._session.add(allocation)
        return allocation

    def save(self, allocation: CustomerReceiptAllocation) -> CustomerReceiptAllocation:
        self._session.add(allocation)
        return allocation

