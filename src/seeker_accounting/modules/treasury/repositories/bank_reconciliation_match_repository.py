from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.treasury.models.bank_reconciliation_match import BankReconciliationMatch


class BankReconciliationMatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_session(self, session_id: int) -> list[BankReconciliationMatch]:
        statement = select(BankReconciliationMatch).where(
            BankReconciliationMatch.reconciliation_session_id == session_id,
        ).order_by(BankReconciliationMatch.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, match_id: int) -> BankReconciliationMatch | None:
        statement = select(BankReconciliationMatch).where(
            BankReconciliationMatch.company_id == company_id,
            BankReconciliationMatch.id == match_id,
        )
        return self._session.scalar(statement)

    def get_total_matched_for_statement_line(
        self,
        statement_line_id: int,
    ) -> Decimal:
        statement = select(func.coalesce(func.sum(BankReconciliationMatch.matched_amount), 0)).where(
            BankReconciliationMatch.bank_statement_line_id == statement_line_id,
        )
        result = self._session.scalar(statement)
        return Decimal(str(result)) if result is not None else Decimal("0.00")

    def add(self, entity: BankReconciliationMatch) -> BankReconciliationMatch:
        self._session.add(entity)
        return entity

    def delete(self, entity: BankReconciliationMatch) -> None:
        self._session.delete(entity)
