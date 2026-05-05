"""Repository for ItemSupplier catalog (P2 / Slice 3.4)."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_supplier import ItemSupplier


class ItemSupplierRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, item_supplier_id: int) -> ItemSupplier | None:
        return self._session.get(ItemSupplier, item_supplier_id)

    def get_by_item_supplier(
        self, company_id: int, item_id: int, supplier_id: int
    ) -> ItemSupplier | None:
        stmt = select(ItemSupplier).where(
            ItemSupplier.company_id == company_id,
            ItemSupplier.item_id == item_id,
            ItemSupplier.supplier_id == supplier_id,
        )
        return self._session.scalars(stmt).first()

    def list_by_item(self, company_id: int, item_id: int) -> Sequence[ItemSupplier]:
        stmt = (
            select(ItemSupplier)
            .where(ItemSupplier.company_id == company_id, ItemSupplier.item_id == item_id)
            .order_by(ItemSupplier.is_preferred.desc(), ItemSupplier.last_purchase_date.desc())
        )
        return self._session.scalars(stmt).all()

    def list_by_supplier(self, company_id: int, supplier_id: int) -> Sequence[ItemSupplier]:
        stmt = select(ItemSupplier).where(
            ItemSupplier.company_id == company_id,
            ItemSupplier.supplier_id == supplier_id,
        )
        return self._session.scalars(stmt).all()

    def get_preferred(self, company_id: int, item_id: int) -> ItemSupplier | None:
        stmt = select(ItemSupplier).where(
            ItemSupplier.company_id == company_id,
            ItemSupplier.item_id == item_id,
            ItemSupplier.is_preferred.is_(True),
        )
        return self._session.scalars(stmt).first()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add(self, row: ItemSupplier) -> None:
        self._session.add(row)

    def delete(self, row: ItemSupplier) -> None:
        self._session.delete(row)
