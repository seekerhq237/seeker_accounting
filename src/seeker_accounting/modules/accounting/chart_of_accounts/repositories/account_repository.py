from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[Account]:
        statement = select(Account).where(Account.company_id == company_id)
        if active_only:
            statement = statement.where(Account.is_active.is_(True))
        statement = statement.order_by(Account.account_code.asc(), Account.id.asc())
        return list(self._session.scalars(statement))

    def list_tree_candidates(self, company_id: int, exclude_account_id: int | None = None) -> list[Account]:
        statement = select(Account).where(Account.company_id == company_id)
        if exclude_account_id is not None:
            statement = statement.where(Account.id != exclude_account_id)
        statement = statement.order_by(Account.account_code.asc(), Account.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, account_id: int) -> Account | None:
        statement = select(Account).where(
            Account.company_id == company_id,
            Account.id == account_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, account_code: str) -> Account | None:
        statement = select(Account).where(
            Account.company_id == company_id,
            Account.account_code == account_code,
        )
        return self._session.scalar(statement)

    def list_children(self, company_id: int, parent_account_id: int | None) -> list[Account]:
        statement = select(Account).where(
            Account.company_id == company_id,
            Account.parent_account_id == parent_account_id,
        )
        statement = statement.order_by(Account.account_code.asc(), Account.id.asc())
        return list(self._session.scalars(statement))

    def add(self, account: Account) -> Account:
        self._session.add(account)
        return account

    def save(self, account: Account) -> Account:
        self._session.add(account)
        return account

    def account_code_exists(
        self,
        company_id: int,
        account_code: str,
        exclude_account_id: int | None = None,
    ) -> bool:
        predicate = (Account.company_id == company_id) & (Account.account_code == account_code)
        if exclude_account_id is not None:
            predicate = predicate & (Account.id != exclude_account_id)
        return bool(self._session.scalar(select(exists().where(predicate))))

