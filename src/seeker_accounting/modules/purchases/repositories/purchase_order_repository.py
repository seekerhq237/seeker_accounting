from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.purchases.models.purchase_order import PurchaseOrder
from seeker_accounting.modules.purchases.models.purchase_order_line import PurchaseOrderLine


class PurchaseOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[PurchaseOrder]:
        statement = select(PurchaseOrder).where(PurchaseOrder.company_id == company_id)
        if status_code is not None:
            statement = statement.where(PurchaseOrder.status_code == status_code)
        statement = statement.options(selectinload(PurchaseOrder.supplier))
        statement = statement.order_by(
            PurchaseOrder.order_date.desc(),
            PurchaseOrder.order_number.desc(),
            PurchaseOrder.id.desc(),
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, order_id: int) -> PurchaseOrder | None:
        statement = select(PurchaseOrder).where(
            PurchaseOrder.company_id == company_id,
            PurchaseOrder.id == order_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, order_id: int) -> PurchaseOrder | None:
        statement = select(PurchaseOrder).where(
            PurchaseOrder.company_id == company_id,
            PurchaseOrder.id == order_id,
        )
        statement = statement.options(
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.currency),
            selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.tax_code),
            selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.expense_account),
        )
        return self._session.scalar(statement)

    def get_by_number(self, company_id: int, order_number: str) -> PurchaseOrder | None:
        statement = select(PurchaseOrder).where(
            PurchaseOrder.company_id == company_id,
            PurchaseOrder.order_number == order_number,
        )
        return self._session.scalar(statement)

    def add(self, order: PurchaseOrder) -> PurchaseOrder:
        self._session.add(order)
        return order

    def save(self, order: PurchaseOrder) -> PurchaseOrder:
        self._session.add(order)
        return order
