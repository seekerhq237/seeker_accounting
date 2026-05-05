from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, nullslast, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_batch import ItemBatch
from seeker_accounting.modules.inventory.models.inventory_cost_layer import InventoryCostLayer


class InventoryCostLayerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_item(
        self,
        company_id: int,
        item_id: int,
        with_remaining_only: bool = False,
        location_id: int | None = None,
        location_aware: bool = False,
        batch_id: int | None = None,
        batch_aware: bool = False,
    ) -> list[InventoryCostLayer]:
        stmt = select(InventoryCostLayer).where(
            InventoryCostLayer.company_id == company_id,
            InventoryCostLayer.item_id == item_id,
        )
        if location_aware:
            if location_id is not None:
                stmt = stmt.where(InventoryCostLayer.location_id == location_id)
            else:
                stmt = stmt.where(InventoryCostLayer.location_id.is_(None))
        if batch_aware:
            if batch_id is not None:
                stmt = stmt.where(InventoryCostLayer.batch_id == batch_id)
            else:
                stmt = stmt.where(InventoryCostLayer.batch_id.is_(None))
        if with_remaining_only:
            stmt = stmt.where(InventoryCostLayer.quantity_remaining > 0)
        stmt = stmt.order_by(InventoryCostLayer.layer_date, InventoryCostLayer.id)
        return list(self._session.scalars(stmt))

    def list_for_item_fefo(
        self,
        company_id: int,
        item_id: int,
        with_remaining_only: bool = False,
        location_id: int | None = None,
        location_aware: bool = False,
        batch_id: int | None = None,
        batch_aware: bool = False,
    ) -> list[InventoryCostLayer]:
        stmt = (
            select(InventoryCostLayer)
            .outerjoin(ItemBatch, InventoryCostLayer.batch_id == ItemBatch.id)
            .where(
                InventoryCostLayer.company_id == company_id,
                InventoryCostLayer.item_id == item_id,
            )
        )
        if location_aware:
            if location_id is not None:
                stmt = stmt.where(InventoryCostLayer.location_id == location_id)
            else:
                stmt = stmt.where(InventoryCostLayer.location_id.is_(None))
        if batch_aware:
            if batch_id is not None:
                stmt = stmt.where(InventoryCostLayer.batch_id == batch_id)
            else:
                stmt = stmt.where(InventoryCostLayer.batch_id.is_(None))
        if with_remaining_only:
            stmt = stmt.where(InventoryCostLayer.quantity_remaining > 0)
        stmt = stmt.order_by(
            nullslast(ItemBatch.expiry_on.asc()),
            InventoryCostLayer.layer_date.asc(),
            InventoryCostLayer.id.asc(),
        )
        return list(self._session.scalars(stmt))

    def get_stock_on_hand(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None = None,
        location_aware: bool = False,
        batch_id: int | None = None,
        batch_aware: bool = False,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(InventoryCostLayer.quantity_remaining), 0)).where(
            InventoryCostLayer.company_id == company_id,
            InventoryCostLayer.item_id == item_id,
        )
        if location_aware:
            if location_id is not None:
                stmt = stmt.where(InventoryCostLayer.location_id == location_id)
            else:
                stmt = stmt.where(InventoryCostLayer.location_id.is_(None))
        if batch_aware:
            if batch_id is not None:
                stmt = stmt.where(InventoryCostLayer.batch_id == batch_id)
            else:
                stmt = stmt.where(InventoryCostLayer.batch_id.is_(None))
        result = self._session.scalar(stmt)
        return Decimal(str(result)) if result is not None else Decimal("0")

    def get_total_value(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None = None,
        location_aware: bool = False,
        batch_id: int | None = None,
        batch_aware: bool = False,
    ) -> Decimal:
        stmt = select(
            func.coalesce(
                func.sum(InventoryCostLayer.quantity_remaining * InventoryCostLayer.unit_cost),
                0,
            )
        ).where(
            InventoryCostLayer.company_id == company_id,
            InventoryCostLayer.item_id == item_id,
        )
        if location_aware:
            if location_id is not None:
                stmt = stmt.where(InventoryCostLayer.location_id == location_id)
            else:
                stmt = stmt.where(InventoryCostLayer.location_id.is_(None))
        if batch_aware:
            if batch_id is not None:
                stmt = stmt.where(InventoryCostLayer.batch_id == batch_id)
            else:
                stmt = stmt.where(InventoryCostLayer.batch_id.is_(None))
        result = self._session.scalar(stmt)
        return Decimal(str(result)) if result is not None else Decimal("0")

    def get_weighted_average_cost(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None = None,
        location_aware: bool = False,
        batch_id: int | None = None,
        batch_aware: bool = False,
    ) -> Decimal | None:
        on_hand = self.get_stock_on_hand(
            company_id,
            item_id,
            location_id=location_id,
            location_aware=location_aware,
            batch_id=batch_id,
            batch_aware=batch_aware,
        )
        if on_hand <= Decimal("0"):
            return None
        total_value = self.get_total_value(
            company_id,
            item_id,
            location_id=location_id,
            location_aware=location_aware,
            batch_id=batch_id,
            batch_aware=batch_aware,
        )
        return (total_value / on_hand).quantize(Decimal("0.0001"))

    def get_by_document_line_id(self, document_line_id: int) -> InventoryCostLayer | None:
        stmt = select(InventoryCostLayer).where(
            InventoryCostLayer.inventory_document_line_id == document_line_id
        )
        return self._session.scalar(stmt)

    def list_all_items_stock(self, company_id: int) -> list[tuple[int, Decimal, Decimal]]:
        """Returns list of (item_id, qty_on_hand, total_value) for all items with stock."""
        stmt = (
            select(
                InventoryCostLayer.item_id,
                func.sum(InventoryCostLayer.quantity_remaining),
                func.sum(InventoryCostLayer.quantity_remaining * InventoryCostLayer.unit_cost),
            )
            .where(InventoryCostLayer.company_id == company_id)
            .group_by(InventoryCostLayer.item_id)
            .having(func.sum(InventoryCostLayer.quantity_remaining) > 0)
        )
        rows = self._session.execute(stmt).all()
        return [
            (row[0], Decimal(str(row[1])), Decimal(str(row[2])))
            for row in rows
        ]

    def add(self, entity: InventoryCostLayer) -> InventoryCostLayer:
        self._session.add(entity)
        return entity

    def save(self, entity: InventoryCostLayer) -> InventoryCostLayer:
        self._session.add(entity)
        return entity
