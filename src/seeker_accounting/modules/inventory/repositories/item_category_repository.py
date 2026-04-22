from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_category import ItemCategory


class ItemCategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[ItemCategory]:
        statement = select(ItemCategory).where(ItemCategory.company_id == company_id)
        if active_only:
            statement = statement.where(ItemCategory.is_active.is_(True))
        statement = statement.order_by(ItemCategory.code.asc(), ItemCategory.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, category_id: int) -> ItemCategory | None:
        statement = select(ItemCategory).where(
            ItemCategory.company_id == company_id,
            ItemCategory.id == category_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, code: str) -> ItemCategory | None:
        statement = select(ItemCategory).where(
            ItemCategory.company_id == company_id,
            ItemCategory.code == code,
        )
        return self._session.scalar(statement)

    def add(self, category: ItemCategory) -> ItemCategory:
        self._session.add(category)
        return category

    def save(self, category: ItemCategory) -> ItemCategory:
        self._session.add(category)
        return category

    def code_exists(self, company_id: int, code: str, exclude_id: int | None = None) -> bool:
        predicate = (ItemCategory.company_id == company_id) & (ItemCategory.code == code)
        if exclude_id is not None:
            predicate = predicate & (ItemCategory.id != exclude_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
