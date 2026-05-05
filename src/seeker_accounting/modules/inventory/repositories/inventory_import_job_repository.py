from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.inventory.models.inventory_import_job import InventoryImportJob


class InventoryImportJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int) -> list[InventoryImportJob]:
        stmt = (
            select(InventoryImportJob)
            .where(InventoryImportJob.company_id == company_id)
            .options(selectinload(InventoryImportJob.rows))
            .order_by(InventoryImportJob.created_at.desc(), InventoryImportJob.id.desc())
        )
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, job_id: int) -> InventoryImportJob | None:
        stmt = (
            select(InventoryImportJob)
            .where(InventoryImportJob.company_id == company_id, InventoryImportJob.id == job_id)
            .options(selectinload(InventoryImportJob.rows))
        )
        return self._session.scalar(stmt)

    def add(self, entity: InventoryImportJob) -> InventoryImportJob:
        self._session.add(entity)
        return entity

    def save(self, entity: InventoryImportJob) -> InventoryImportJob:
        self._session.add(entity)
        return entity