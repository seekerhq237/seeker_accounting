from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType


class AccountTypeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self, active_only: bool = False) -> list[AccountType]:
        statement = select(AccountType)
        if active_only:
            statement = statement.where(AccountType.is_active.is_(True))
        statement = statement.order_by(AccountType.name.asc(), AccountType.code.asc(), AccountType.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, account_type_id: int) -> AccountType | None:
        return self._session.get(AccountType, account_type_id)

    def get_by_code(self, code: str) -> AccountType | None:
        return self._session.scalar(select(AccountType).where(AccountType.code == code))

    def add(self, account_type: AccountType) -> AccountType:
        self._session.add(account_type)
        return account_type

    def save(self, account_type: AccountType) -> AccountType:
        self._session.add(account_type)
        return account_type
