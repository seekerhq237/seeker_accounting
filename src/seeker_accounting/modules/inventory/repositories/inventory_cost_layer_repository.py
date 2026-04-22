from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.inventory_cost_layer import InventoryCostLayer


class InventoryCostLayerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_item(
        self,
        company_id: int,
        item_id: int,
        with_remaining_only: bool = False,
    ) -> list[InventoryCostLayer]:
        stmt = select(InventoryCostLayer).where(
            InventoryCostLayer.company_id == company_id,
            InventoryCostLayer.item_id == item_id,
        )
        if with_remaining_only:
            stmt = stmt.where(InventoryCostLayer.quantity_remaining > 0)
        stmt = stmt.order_by(InventoryCostLayer.layer_date, InventoryCostLayer.id)
        return list(self._session.scalars(stmt))

    def get_stock_on_hand(self, company_id: int, item_id: int) -> Decimal:
        result = self._session.scalar(
            select(func.coalesce(func.sum(InventoryCostLayer.quantity_remaining), 0)).where(
                InventoryCostLayer.company_id == company_id,
                InventoryCostLayer.item_id == item_id,
            )
        )
        return Decimal(str(result)) if result is not None else Decimal("0")

    def get_total_value(self, company_id: int, item_id: int) -> Decimal:
        result = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(InventoryCostLayer.quantity_remaining * InventoryCostLayer.unit_cost),
                    0,
                )
            ).where(
                InventoryCostLayer.company_id == company_id,
                InventoryCostLayer.item_id == item_id,
            )
        )
        return Decimal(str(result)) if result is not None else Decimal("0")

    def get_weighted_average_cost(self, company_id: int, item_id: int) -> Decimal | None:
        on_hand = self.get_stock_on_hand(company_id, item_id)
        if on_hand <= Decimal("0"):
            return None
        total_value = self.get_total_value(company_id, item_id)
        return (total_value / on_hand).quantize(Decimal("0.0001"))

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
