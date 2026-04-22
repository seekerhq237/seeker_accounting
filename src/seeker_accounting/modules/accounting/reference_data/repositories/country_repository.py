from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.country import Country


class CountryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_code(self, country_code: str) -> Country | None:
        statement = select(Country).where(Country.code == country_code)
        return self._session.scalar(statement)

    def add(self, country: Country) -> None:
        self._session.add(country)

    def exists_active(self, country_code: str) -> bool:
        statement = select(exists().where(Country.code == country_code).where(Country.is_active.is_(True)))
        return bool(self._session.scalar(statement))

    def list_active(self) -> list[Country]:
        statement = (
            select(Country)
            .where(Country.is_active.is_(True))
            .order_by(Country.name.asc(), Country.code.asc())
        )
        return list(self._session.scalars(statement))
