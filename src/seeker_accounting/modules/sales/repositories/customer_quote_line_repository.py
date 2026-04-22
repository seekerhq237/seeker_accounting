from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.sales.models.customer_quote import CustomerQuote
from seeker_accounting.modules.sales.models.customer_quote_line import CustomerQuoteLine


class CustomerQuoteLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_quote(self, company_id: int, customer_quote_id: int) -> list[CustomerQuoteLine]:
        statement = (
            select(CustomerQuoteLine)
            .join(CustomerQuote, CustomerQuote.id == CustomerQuoteLine.customer_quote_id)
            .where(
                CustomerQuote.company_id == company_id,
                CustomerQuoteLine.customer_quote_id == customer_quote_id,
            )
            .order_by(CustomerQuoteLine.line_number.asc(), CustomerQuoteLine.id.asc())
        )
        return list(self._session.scalars(statement))

    def replace_lines(
        self,
        company_id: int,
        customer_quote_id: int,
        lines: list[CustomerQuoteLine],
    ) -> list[CustomerQuoteLine]:
        for existing_line in self.list_for_quote(company_id, customer_quote_id):
            self._session.delete(existing_line)
        self._session.flush()
        for line in lines:
            line.customer_quote_id = customer_quote_id
            self._session.add(line)
        return lines

    def add(self, line: CustomerQuoteLine) -> CustomerQuoteLine:
        self._session.add(line)
        return line

    def save(self, line: CustomerQuoteLine) -> CustomerQuoteLine:
        self._session.add(line)
        return line
