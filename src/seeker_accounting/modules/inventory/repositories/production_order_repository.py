from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.inventory.models.production_order import ProductionOrder


class ProductionOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int) -> list[ProductionOrder]:
        stmt = (
            select(ProductionOrder)
            .where(ProductionOrder.company_id == company_id)
            .options(selectinload(ProductionOrder.bom), selectinload(ProductionOrder.finished_item))
            .order_by(ProductionOrder.order_date.desc(), ProductionOrder.id.desc())
        )
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, production_order_id: int) -> ProductionOrder | None:
        stmt = (
            select(ProductionOrder)
            .where(ProductionOrder.company_id == company_id, ProductionOrder.id == production_order_id)
            .options(selectinload(ProductionOrder.bom), selectinload(ProductionOrder.finished_item))
        )
        return self._session.scalar(stmt)

    def add(self, entity: ProductionOrder) -> ProductionOrder:
        self._session.add(entity)
        return entity

    def save(self, entity: ProductionOrder) -> ProductionOrder:
        self._session.add(entity)
        return entity