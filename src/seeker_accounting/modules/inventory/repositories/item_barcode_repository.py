"""Repository for ItemBarcode (P6 / Slice 7.5)."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_barcode import ItemBarcode


class ItemBarcodeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, barcode_id: int) -> ItemBarcode | None:
        return self._session.get(ItemBarcode, barcode_id)

    def find_by_barcode(self, company_id: int, barcode: str) -> ItemBarcode | None:
        stmt = select(ItemBarcode).where(
            ItemBarcode.company_id == company_id,
            ItemBarcode.barcode == barcode,
        )
        return self._session.scalars(stmt).first()

    def list_for_item(self, item_id: int) -> Sequence[ItemBarcode]:
        stmt = (
            select(ItemBarcode)
            .where(ItemBarcode.item_id == item_id)
            .order_by(ItemBarcode.is_primary.desc())
        )
        return self._session.scalars(stmt).all()

    def get_primary(self, item_id: int) -> ItemBarcode | None:
        stmt = select(ItemBarcode).where(
            ItemBarcode.item_id == item_id, ItemBarcode.is_primary.is_(True)
        )
        return self._session.scalars(stmt).first()

    def add(self, barcode: ItemBarcode) -> None:
        self._session.add(barcode)

    def delete(self, barcode: ItemBarcode) -> None:
        self._session.delete(barcode)
