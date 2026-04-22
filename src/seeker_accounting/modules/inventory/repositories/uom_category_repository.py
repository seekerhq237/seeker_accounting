from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.uom_category import UomCategory


class UomCategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[UomCategory]:
        statement = select(UomCategory).where(UomCategory.company_id == company_id)
        if active_only:
            statement = statement.where(UomCategory.is_active.is_(True))
        statement = statement.order_by(UomCategory.code.asc(), UomCategory.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, category_id: int) -> UomCategory | None:
        statement = select(UomCategory).where(
            UomCategory.company_id == company_id,
            UomCategory.id == category_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, code: str) -> UomCategory | None:
        statement = select(UomCategory).where(
            UomCategory.company_id == company_id,
            UomCategory.code == code,
        )
        return self._session.scalar(statement)

    def add(self, category: UomCategory) -> UomCategory:
        self._session.add(category)
        return category

    def save(self, category: UomCategory) -> UomCategory:
        self._session.add(category)
        return category

    def code_exists(self, company_id: int, code: str, exclude_id: int | None = None) -> bool:
        predicate = (UomCategory.company_id == company_id) & (UomCategory.code == code)
        if exclude_id is not None:
            predicate = predicate & (UomCategory.id != exclude_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
