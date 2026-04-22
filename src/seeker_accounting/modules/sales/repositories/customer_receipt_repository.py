from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.sales.models.customer_receipt import CustomerReceipt
from seeker_accounting.modules.sales.models.customer_receipt_allocation import CustomerReceiptAllocation


class CustomerReceiptRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, status_code: str | None = None) -> list[CustomerReceipt]:
        statement = select(CustomerReceipt).where(CustomerReceipt.company_id == company_id)
        if status_code is not None:
            statement = statement.where(CustomerReceipt.status_code == status_code)
        statement = statement.options(selectinload(CustomerReceipt.customer), selectinload(CustomerReceipt.financial_account))
        statement = statement.order_by(
            CustomerReceipt.receipt_date.desc(),
            CustomerReceipt.receipt_number.desc(),
            CustomerReceipt.id.desc(),
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, receipt_id: int) -> CustomerReceipt | None:
        statement = select(CustomerReceipt).where(
            CustomerReceipt.company_id == company_id,
            CustomerReceipt.id == receipt_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, receipt_id: int) -> CustomerReceipt | None:
        statement = select(CustomerReceipt).where(
            CustomerReceipt.company_id == company_id,
            CustomerReceipt.id == receipt_id,
        )
        statement = statement.options(
            selectinload(CustomerReceipt.customer),
            selectinload(CustomerReceipt.currency),
            selectinload(CustomerReceipt.financial_account),
            selectinload(CustomerReceipt.posted_journal_entry),
            selectinload(CustomerReceipt.posted_by_user),
            selectinload(CustomerReceipt.allocations)
            .selectinload(CustomerReceiptAllocation.sales_invoice),
        )
        return self._session.scalar(statement)

    def get_by_number(self, company_id: int, receipt_number: str) -> CustomerReceipt | None:
        statement = select(CustomerReceipt).where(
            CustomerReceipt.company_id == company_id,
            CustomerReceipt.receipt_number == receipt_number,
        )
        return self._session.scalar(statement)

    def add(self, receipt: CustomerReceipt) -> CustomerReceipt:
        self._session.add(receipt)
        return receipt

    def save(self, receipt: CustomerReceipt) -> CustomerReceipt:
        self._session.add(receipt)
        return receipt

