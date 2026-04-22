from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.treasury.models.treasury_transaction_line import TreasuryTransactionLine


class TreasuryTransactionLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_transaction(self, transaction_id: int) -> list[TreasuryTransactionLine]:
        statement = select(TreasuryTransactionLine).where(
            TreasuryTransactionLine.treasury_transaction_id == transaction_id,
        ).order_by(TreasuryTransactionLine.line_number.asc())
        return list(self._session.scalars(statement))

    def add(self, entity: TreasuryTransactionLine) -> TreasuryTransactionLine:
        self._session.add(entity)
        return entity

    def delete_for_transaction(self, transaction_id: int) -> None:
        lines = self.list_for_transaction(transaction_id)
        for line in lines:
            self._session.delete(line)
