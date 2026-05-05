from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_batch import ItemBatch


class ItemBatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_item(self, company_id: int, item_id: int | None = None) -> list[ItemBatch]:
        stmt = select(ItemBatch).where(ItemBatch.company_id == company_id)
        if item_id is not None:
            stmt = stmt.where(ItemBatch.item_id == item_id)
        stmt = stmt.order_by(ItemBatch.item_id, ItemBatch.batch_number)
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, batch_id: int) -> ItemBatch | None:
        stmt = select(ItemBatch).where(
            ItemBatch.company_id == company_id,
            ItemBatch.id == batch_id,
        )
        return self._session.scalar(stmt)

    def get_by_number(self, company_id: int, item_id: int, batch_number: str) -> ItemBatch | None:
        stmt = select(ItemBatch).where(
            ItemBatch.company_id == company_id,
            ItemBatch.item_id == item_id,
            ItemBatch.batch_number == batch_number,
        )
        return self._session.scalar(stmt)

    def add(self, entity: ItemBatch) -> ItemBatch:
        self._session.add(entity)
        return entity

    def save(self, entity: ItemBatch) -> ItemBatch:
        self._session.add(entity)
        return entity