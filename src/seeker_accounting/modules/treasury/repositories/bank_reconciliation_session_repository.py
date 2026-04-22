from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.treasury.models.bank_reconciliation_session import BankReconciliationSession


class BankReconciliationSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        financial_account_id: int | None = None,
    ) -> list[BankReconciliationSession]:
        statement = select(BankReconciliationSession).where(
            BankReconciliationSession.company_id == company_id
        )
        if financial_account_id is not None:
            statement = statement.where(
                BankReconciliationSession.financial_account_id == financial_account_id
            )
        statement = statement.options(
            selectinload(BankReconciliationSession.financial_account),
        )
        statement = statement.order_by(
            BankReconciliationSession.statement_end_date.desc(),
            BankReconciliationSession.id.desc(),
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, session_id: int) -> BankReconciliationSession | None:
        statement = select(BankReconciliationSession).where(
            BankReconciliationSession.company_id == company_id,
            BankReconciliationSession.id == session_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, session_id: int) -> BankReconciliationSession | None:
        statement = select(BankReconciliationSession).where(
            BankReconciliationSession.company_id == company_id,
            BankReconciliationSession.id == session_id,
        ).options(
            selectinload(BankReconciliationSession.financial_account),
            selectinload(BankReconciliationSession.matches),
        )
        return self._session.scalar(statement)

    def add(self, entity: BankReconciliationSession) -> BankReconciliationSession:
        self._session.add(entity)
        return entity

    def save(self, entity: BankReconciliationSession) -> BankReconciliationSession:
        self._session.add(entity)
        return entity
