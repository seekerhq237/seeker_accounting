from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.purchases.models.purchase_bill import PurchaseBill
from seeker_accounting.modules.purchases.models.purchase_bill_line import PurchaseBillLine


class PurchaseBillLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_bill(self, company_id: int, purchase_bill_id: int) -> list[PurchaseBillLine]:
        statement = (
            select(PurchaseBillLine)
            .join(PurchaseBill, PurchaseBill.id == PurchaseBillLine.purchase_bill_id)
            .where(
                PurchaseBill.company_id == company_id,
                PurchaseBillLine.purchase_bill_id == purchase_bill_id,
            )
            .order_by(PurchaseBillLine.line_number.asc(), PurchaseBillLine.id.asc())
        )
        return list(self._session.scalars(statement))

    def replace_lines(self, company_id: int, purchase_bill_id: int, lines: list[PurchaseBillLine]) -> list[PurchaseBillLine]:
        for existing_line in self.list_for_bill(company_id, purchase_bill_id):
            self._session.delete(existing_line)
        self._session.flush()
        for line in lines:
            line.purchase_bill_id = purchase_bill_id
            self._session.add(line)
        return lines

    def add(self, line: PurchaseBillLine) -> PurchaseBillLine:
        self._session.add(line)
        return line

    def save(self, line: PurchaseBillLine) -> PurchaseBillLine:
        self._session.add(line)
        return line
