from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.sales.models.sales_invoice import SalesInvoice
from seeker_accounting.modules.sales.models.sales_invoice_line import SalesInvoiceLine


class SalesInvoiceLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_invoice(self, company_id: int, sales_invoice_id: int) -> list[SalesInvoiceLine]:
        statement = (
            select(SalesInvoiceLine)
            .join(SalesInvoice, SalesInvoice.id == SalesInvoiceLine.sales_invoice_id)
            .where(
                SalesInvoice.company_id == company_id,
                SalesInvoiceLine.sales_invoice_id == sales_invoice_id,
            )
            .order_by(SalesInvoiceLine.line_number.asc(), SalesInvoiceLine.id.asc())
        )
        return list(self._session.scalars(statement))

    def replace_lines(self, company_id: int, sales_invoice_id: int, lines: list[SalesInvoiceLine]) -> list[SalesInvoiceLine]:
        for existing_line in self.list_for_invoice(company_id, sales_invoice_id):
            self._session.delete(existing_line)
        self._session.flush()
        for line in lines:
            line.sales_invoice_id = sales_invoice_id
            self._session.add(line)
        return lines

    def add(self, line: SalesInvoiceLine) -> SalesInvoiceLine:
        self._session.add(line)
        return line

    def save(self, line: SalesInvoiceLine) -> SalesInvoiceLine:
        self._session.add(line)
        return line

