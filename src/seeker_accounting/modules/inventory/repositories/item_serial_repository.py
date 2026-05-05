from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_serial import ItemSerial


class ItemSerialRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_item(self, company_id: int, item_id: int | None = None) -> list[ItemSerial]:
        stmt = select(ItemSerial).where(ItemSerial.company_id == company_id)
        if item_id is not None:
            stmt = stmt.where(ItemSerial.item_id == item_id)
        stmt = stmt.order_by(ItemSerial.item_id, ItemSerial.serial_number)
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, serial_id: int) -> ItemSerial | None:
        stmt = select(ItemSerial).where(
            ItemSerial.company_id == company_id,
            ItemSerial.id == serial_id,
        )
        return self._session.scalar(stmt)

    def get_by_number(self, company_id: int, item_id: int, serial_number: str) -> ItemSerial | None:
        stmt = select(ItemSerial).where(
            ItemSerial.company_id == company_id,
            ItemSerial.item_id == item_id,
            ItemSerial.serial_number == serial_number,
        )
        return self._session.scalar(stmt)

    def add(self, entity: ItemSerial) -> ItemSerial:
        self._session.add(entity)
        return entity

    def save(self, entity: ItemSerial) -> ItemSerial:
        self._session.add(entity)
        return entity