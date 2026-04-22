from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine
from seeker_accounting.modules.sales.models.customer_receipt_allocation import CustomerReceiptAllocation


class SalesInvoiceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
    ) -> list[SalesInvoice]:
        statement = select(SalesInvoice).where(SalesInvoice.company_id == company_id)
        if status_code is not None:
            statement = statement.where(SalesInvoice.status_code == status_code)
        if payment_status_code is not None:
            statement = statement.where(SalesInvoice.payment_status_code == payment_status_code)
        statement = statement.options(selectinload(SalesInvoice.customer))
        statement = statement.order_by(
            SalesInvoice.invoice_date.desc(),
            SalesInvoice.invoice_number.desc(),
            SalesInvoice.id.desc(),
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, invoice_id: int) -> SalesInvoice | None:
        statement = select(SalesInvoice).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.id == invoice_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, invoice_id: int) -> SalesInvoice | None:
        statement = select(SalesInvoice).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.id == invoice_id,
        )
        statement = statement.options(
            selectinload(SalesInvoice.customer),
            selectinload(SalesInvoice.currency),
            selectinload(SalesInvoice.posted_journal_entry),
            selectinload(SalesInvoice.posted_by_user),
            selectinload(SalesInvoice.lines)
            .selectinload(SalesInvoiceLine.tax_code),
            selectinload(SalesInvoice.lines)
            .selectinload(SalesInvoiceLine.revenue_account),
            selectinload(SalesInvoice.allocations).selectinload(CustomerReceiptAllocation.customer_receipt),
        )
        return self._session.scalar(statement)

    def get_by_number(self, company_id: int, invoice_number: str) -> SalesInvoice | None:
        statement = select(SalesInvoice).where(
            SalesInvoice.company_id == company_id,
            SalesInvoice.invoice_number == invoice_number,
        )
        return self._session.scalar(statement)

    def add(self, invoice: SalesInvoice) -> SalesInvoice:
        self._session.add(invoice)
        return invoice

    def save(self, invoice: SalesInvoice) -> SalesInvoice:
        self._session.add(invoice)
        return invoice
