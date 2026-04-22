from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount


class FinancialAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[FinancialAccount]:
        statement = select(FinancialAccount).where(FinancialAccount.company_id == company_id)
        if active_only:
            statement = statement.where(FinancialAccount.is_active.is_(True))
        statement = statement.options(
            selectinload(FinancialAccount.gl_account),
            selectinload(FinancialAccount.currency),
        )
        statement = statement.order_by(FinancialAccount.name.asc(), FinancialAccount.account_code.asc(), FinancialAccount.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, financial_account_id: int) -> FinancialAccount | None:
        statement = select(FinancialAccount).where(
            FinancialAccount.company_id == company_id,
            FinancialAccount.id == financial_account_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, account_code: str) -> FinancialAccount | None:
        statement = select(FinancialAccount).where(
            FinancialAccount.company_id == company_id,
            FinancialAccount.account_code == account_code,
        )
        return self._session.scalar(statement)

    def add(self, financial_account: FinancialAccount) -> FinancialAccount:
        self._session.add(financial_account)
        return financial_account

    def save(self, financial_account: FinancialAccount) -> FinancialAccount:
        self._session.add(financial_account)
        return financial_account

    def account_code_exists(
        self,
        company_id: int,
        account_code: str,
        exclude_financial_account_id: int | None = None,
    ) -> bool:
        predicate = (
            (FinancialAccount.company_id == company_id)
            & (FinancialAccount.account_code == account_code)
        )
        if exclude_financial_account_id is not None:
            predicate = predicate & (FinancialAccount.id != exclude_financial_account_id)
        return bool(self._session.scalar(select(exists().where(predicate))))

