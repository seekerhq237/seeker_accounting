from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, joinedload

from seeker_accounting.modules.inventory.models.unit_of_measure import UnitOfMeasure


class UnitOfMeasureRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[UnitOfMeasure]:
        statement = (
            select(UnitOfMeasure)
            .options(joinedload(UnitOfMeasure.category))
            .where(UnitOfMeasure.company_id == company_id)
        )
        if active_only:
            statement = statement.where(UnitOfMeasure.is_active.is_(True))
        statement = statement.order_by(UnitOfMeasure.code.asc(), UnitOfMeasure.id.asc())
        return list(self._session.scalars(statement.distinct()))

    def get_by_id(self, company_id: int, uom_id: int) -> UnitOfMeasure | None:
        statement = (
            select(UnitOfMeasure)
            .options(joinedload(UnitOfMeasure.category))
            .where(
                UnitOfMeasure.company_id == company_id,
                UnitOfMeasure.id == uom_id,
            )
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, code: str) -> UnitOfMeasure | None:
        statement = select(UnitOfMeasure).where(
            UnitOfMeasure.company_id == company_id,
            UnitOfMeasure.code == code,
        )
        return self._session.scalar(statement)

    def add(self, uom: UnitOfMeasure) -> UnitOfMeasure:
        self._session.add(uom)
        return uom

    def save(self, uom: UnitOfMeasure) -> UnitOfMeasure:
        self._session.add(uom)
        return uom

    def code_exists(self, company_id: int, code: str, exclude_id: int | None = None) -> bool:
        predicate = (UnitOfMeasure.company_id == company_id) & (UnitOfMeasure.code == code)
        if exclude_id is not None:
            predicate = predicate & (UnitOfMeasure.id != exclude_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
