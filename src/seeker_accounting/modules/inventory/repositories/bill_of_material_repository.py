from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.inventory.models.bill_of_material import BillOfMaterial


class BillOfMaterialRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, item_id: int | None = None) -> list[BillOfMaterial]:
        stmt = select(BillOfMaterial).where(BillOfMaterial.company_id == company_id)
        if item_id is not None:
            stmt = stmt.where(BillOfMaterial.item_id == item_id)
        stmt = stmt.options(selectinload(BillOfMaterial.components))
        stmt = stmt.order_by(BillOfMaterial.item_id, BillOfMaterial.version)
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, bom_id: int) -> BillOfMaterial | None:
        stmt = (
            select(BillOfMaterial)
            .where(BillOfMaterial.company_id == company_id, BillOfMaterial.id == bom_id)
            .options(selectinload(BillOfMaterial.components))
        )
        return self._session.scalar(stmt)

    def get_by_version(self, company_id: int, item_id: int, version: str) -> BillOfMaterial | None:
        stmt = select(BillOfMaterial).where(
            BillOfMaterial.company_id == company_id,
            BillOfMaterial.item_id == item_id,
            BillOfMaterial.version == version,
        )
        return self._session.scalar(stmt)

    def add(self, entity: BillOfMaterial) -> BillOfMaterial:
        self._session.add(entity)
        return entity

    def save(self, entity: BillOfMaterial) -> BillOfMaterial:
        self._session.add(entity)
        return entity