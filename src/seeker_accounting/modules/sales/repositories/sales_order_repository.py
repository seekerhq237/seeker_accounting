from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.sales.models.sales_order import SalesOrder
from seeker_accounting.modules.sales.models.sales_order_line import SalesOrderLine


class SalesOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[SalesOrder]:
        statement = select(SalesOrder).where(SalesOrder.company_id == company_id)
        if status_code is not None:
            statement = statement.where(SalesOrder.status_code == status_code)
        statement = statement.options(selectinload(SalesOrder.customer))
        statement = statement.order_by(
            SalesOrder.order_date.desc(),
            SalesOrder.order_number.desc(),
            SalesOrder.id.desc(),
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, order_id: int) -> SalesOrder | None:
        statement = select(SalesOrder).where(
            SalesOrder.company_id == company_id,
            SalesOrder.id == order_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, order_id: int) -> SalesOrder | None:
        statement = select(SalesOrder).where(
            SalesOrder.company_id == company_id,
            SalesOrder.id == order_id,
        )
        statement = statement.options(
            selectinload(SalesOrder.customer),
            selectinload(SalesOrder.currency),
            selectinload(SalesOrder.lines).selectinload(SalesOrderLine.tax_code),
            selectinload(SalesOrder.lines).selectinload(SalesOrderLine.revenue_account),
        )
        return self._session.scalar(statement)

    def get_by_number(self, company_id: int, order_number: str) -> SalesOrder | None:
        statement = select(SalesOrder).where(
            SalesOrder.company_id == company_id,
            SalesOrder.order_number == order_number,
        )
        return self._session.scalar(statement)

    def add(self, order: SalesOrder) -> SalesOrder:
        self._session.add(order)
        return order

    def save(self, order: SalesOrder) -> SalesOrder:
        self._session.add(order)
        return order
