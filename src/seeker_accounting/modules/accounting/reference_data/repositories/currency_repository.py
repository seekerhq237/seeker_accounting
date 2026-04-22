from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.currency import Currency


class CurrencyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_code(self, currency_code: str) -> Currency | None:
        statement = select(Currency).where(Currency.code == currency_code)
        return self._session.scalar(statement)

    def add(self, currency: Currency) -> None:
        self._session.add(currency)

    def exists_active(self, currency_code: str) -> bool:
        statement = select(exists().where(Currency.code == currency_code).where(Currency.is_active.is_(True)))
        return bool(self._session.scalar(statement))

    def list_active(self) -> list[Currency]:
        statement = (
            select(Currency)
            .where(Currency.is_active.is_(True))
            .order_by(Currency.name.asc(), Currency.code.asc())
        )
        return list(self._session.scalars(statement))
