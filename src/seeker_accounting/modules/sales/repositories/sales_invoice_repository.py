from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.customers.models.customer import Customer
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

    # ------------------------------------------------------------------
    # Paginated + searchable listing (server-side)
    # ------------------------------------------------------------------

    def _build_filter_conditions(
        self,
        company_id: int,
        status_code: str | None,
        payment_status_code: str | None,
        query: str | None,
    ) -> list:
        conditions: list = [SalesInvoice.company_id == company_id]
        if status_code is not None:
            conditions.append(SalesInvoice.status_code == status_code)
        if payment_status_code is not None:
            conditions.append(SalesInvoice.payment_status_code == payment_status_code)
        if query:
            like = f"%{query.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(SalesInvoice.invoice_number).like(like),
                    func.lower(SalesInvoice.reference_number).like(like),
                    func.lower(Customer.display_name).like(like),
                    func.lower(Customer.customer_code).like(like),
                )
            )
        return conditions

    def count_filtered(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
        query: str | None = None,
    ) -> int:
        stmt = (
            select(func.count(SalesInvoice.id))
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .where(*self._build_filter_conditions(company_id, status_code, payment_status_code, query))
        )
        return int(self._session.scalar(stmt) or 0)

    def list_filtered_page(
        self,
        company_id: int,
        status_code: str | None = None,
        payment_status_code: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SalesInvoice]:
        stmt = (
            select(SalesInvoice)
            .join(Customer, Customer.id == SalesInvoice.customer_id)
            .where(*self._build_filter_conditions(company_id, status_code, payment_status_code, query))
            .options(selectinload(SalesInvoice.customer))
            .order_by(
                SalesInvoice.invoice_date.desc(),
                SalesInvoice.invoice_number.desc(),
                SalesInvoice.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt))

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
