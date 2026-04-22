from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.purchases.models.purchase_order import PurchaseOrder
from seeker_accounting.modules.purchases.models.purchase_order_line import PurchaseOrderLine


class PurchaseOrderLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_order(self, company_id: int, purchase_order_id: int) -> list[PurchaseOrderLine]:
        statement = (
            select(PurchaseOrderLine)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .where(
                PurchaseOrder.company_id == company_id,
                PurchaseOrderLine.purchase_order_id == purchase_order_id,
            )
            .order_by(PurchaseOrderLine.line_number.asc(), PurchaseOrderLine.id.asc())
        )
        return list(self._session.scalars(statement))

    def replace_lines(
        self,
        company_id: int,
        purchase_order_id: int,
        lines: list[PurchaseOrderLine],
    ) -> list[PurchaseOrderLine]:
        for existing_line in self.list_for_order(company_id, purchase_order_id):
            self._session.delete(existing_line)
        self._session.flush()
        for line in lines:
            line.purchase_order_id = purchase_order_id
            self._session.add(line)
        return lines

    def add(self, line: PurchaseOrderLine) -> PurchaseOrderLine:
        self._session.add(line)
        return line

    def save(self, line: PurchaseOrderLine) -> PurchaseOrderLine:
        self._session.add(line)
        return line
