from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.sales.models.sales_order import SalesOrder
from seeker_accounting.modules.sales.models.sales_order_line import SalesOrderLine


class SalesOrderLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_order(self, company_id: int, sales_order_id: int) -> list[SalesOrderLine]:
        statement = (
            select(SalesOrderLine)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .where(
                SalesOrder.company_id == company_id,
                SalesOrderLine.sales_order_id == sales_order_id,
            )
            .order_by(SalesOrderLine.line_number.asc(), SalesOrderLine.id.asc())
        )
        return list(self._session.scalars(statement))

    def replace_lines(
        self,
        company_id: int,
        sales_order_id: int,
        lines: list[SalesOrderLine],
    ) -> list[SalesOrderLine]:
        for existing_line in self.list_for_order(company_id, sales_order_id):
            self._session.delete(existing_line)
        self._session.flush()
        for line in lines:
            line.sales_order_id = sales_order_id
            self._session.add(line)
        return lines

    def add(self, line: SalesOrderLine) -> SalesOrderLine:
        self._session.add(line)
        return line

    def save(self, line: SalesOrderLine) -> SalesOrderLine:
        self._session.add(line)
        return line
