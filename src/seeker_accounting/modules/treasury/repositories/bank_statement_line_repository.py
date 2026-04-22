from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.treasury.models.bank_statement_line import BankStatementLine


class BankStatementLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_financial_account(
        self,
        company_id: int,
        financial_account_id: int,
        reconciled_only: bool | None = None,
    ) -> list[BankStatementLine]:
        statement = select(BankStatementLine).where(
            BankStatementLine.company_id == company_id,
            BankStatementLine.financial_account_id == financial_account_id,
        )
        if reconciled_only is True:
            statement = statement.where(BankStatementLine.is_reconciled.is_(True))
        elif reconciled_only is False:
            statement = statement.where(BankStatementLine.is_reconciled.is_(False))
        statement = statement.order_by(BankStatementLine.line_date.desc(), BankStatementLine.id.desc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, line_id: int) -> BankStatementLine | None:
        statement = select(BankStatementLine).where(
            BankStatementLine.company_id == company_id,
            BankStatementLine.id == line_id,
        )
        return self._session.scalar(statement)

    def add(self, entity: BankStatementLine) -> BankStatementLine:
        self._session.add(entity)
        return entity

    def save(self, entity: BankStatementLine) -> BankStatementLine:
        self._session.add(entity)
        return entity
