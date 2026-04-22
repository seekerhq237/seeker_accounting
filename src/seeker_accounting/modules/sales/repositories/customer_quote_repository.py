from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.sales.models.customer_quote import CustomerQuote
from seeker_accounting.modules.sales.models.customer_quote_line import CustomerQuoteLine


class CustomerQuoteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[CustomerQuote]:
        statement = select(CustomerQuote).where(CustomerQuote.company_id == company_id)
        if status_code is not None:
            statement = statement.where(CustomerQuote.status_code == status_code)
        statement = statement.options(selectinload(CustomerQuote.customer))
        statement = statement.order_by(
            CustomerQuote.quote_date.desc(),
            CustomerQuote.quote_number.desc(),
            CustomerQuote.id.desc(),
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, quote_id: int) -> CustomerQuote | None:
        statement = select(CustomerQuote).where(
            CustomerQuote.company_id == company_id,
            CustomerQuote.id == quote_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, quote_id: int) -> CustomerQuote | None:
        statement = select(CustomerQuote).where(
            CustomerQuote.company_id == company_id,
            CustomerQuote.id == quote_id,
        )
        statement = statement.options(
            selectinload(CustomerQuote.customer),
            selectinload(CustomerQuote.currency),
            selectinload(CustomerQuote.lines).selectinload(CustomerQuoteLine.tax_code),
            selectinload(CustomerQuote.lines).selectinload(CustomerQuoteLine.revenue_account),
        )
        return self._session.scalar(statement)

    def get_by_number(self, company_id: int, quote_number: str) -> CustomerQuote | None:
        statement = select(CustomerQuote).where(
            CustomerQuote.company_id == company_id,
            CustomerQuote.quote_number == quote_number,
        )
        return self._session.scalar(statement)

    def add(self, quote: CustomerQuote) -> CustomerQuote:
        self._session.add(quote)
        return quote

    def save(self, quote: CustomerQuote) -> CustomerQuote:
        self._session.add(quote)
        return quote
