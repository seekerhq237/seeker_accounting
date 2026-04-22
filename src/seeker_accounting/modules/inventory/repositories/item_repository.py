from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item import Item


class ItemRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        active_only: bool = False,
        item_type_code: str | None = None,
    ) -> list[Item]:
        stmt = select(Item).where(Item.company_id == company_id)
        if active_only:
            stmt = stmt.where(Item.is_active.is_(True))
        if item_type_code is not None:
            stmt = stmt.where(Item.item_type_code == item_type_code)
        stmt = stmt.order_by(Item.item_code)
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, item_id: int) -> Item | None:
        stmt = select(Item).where(Item.company_id == company_id, Item.id == item_id)
        return self._session.scalar(stmt)

    def get_by_code(self, company_id: int, item_code: str) -> Item | None:
        stmt = select(Item).where(Item.company_id == company_id, Item.item_code == item_code)
        return self._session.scalar(stmt)

    def add(self, entity: Item) -> Item:
        self._session.add(entity)
        return entity

    def save(self, entity: Item) -> Item:
        self._session.add(entity)
        return entity
