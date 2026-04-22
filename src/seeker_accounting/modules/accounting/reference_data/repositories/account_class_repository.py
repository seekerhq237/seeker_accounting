from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass


class AccountClassRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self, active_only: bool = False) -> list[AccountClass]:
        statement = select(AccountClass)
        if active_only:
            statement = statement.where(AccountClass.is_active.is_(True))
        statement = statement.order_by(AccountClass.display_order.asc(), AccountClass.code.asc(), AccountClass.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, account_class_id: int) -> AccountClass | None:
        return self._session.get(AccountClass, account_class_id)

    def get_by_code(self, code: str) -> AccountClass | None:
        return self._session.scalar(select(AccountClass).where(AccountClass.code == code))

    def add(self, account_class: AccountClass) -> AccountClass:
        self._session.add(account_class)
        return account_class

    def save(self, account_class: AccountClass) -> AccountClass:
        self._session.add(account_class)
        return account_class
