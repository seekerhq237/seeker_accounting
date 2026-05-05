from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.inventory_document_type import (
    InventoryDocumentType,
)


class InventoryDocumentTypeRepository:
    """Repository for the per-company inventory document type taxonomy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self, company_id: int, active_only: bool = False
    ) -> list[InventoryDocumentType]:
        statement = select(InventoryDocumentType).where(
            InventoryDocumentType.company_id == company_id
        )
        if active_only:
            statement = statement.where(InventoryDocumentType.is_active.is_(True))
        statement = statement.order_by(
            InventoryDocumentType.code.asc(), InventoryDocumentType.id.asc()
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, type_id: int) -> InventoryDocumentType | None:
        return self._session.scalar(
            select(InventoryDocumentType).where(
                InventoryDocumentType.company_id == company_id,
                InventoryDocumentType.id == type_id,
            )
        )

    def get_by_code(self, company_id: int, code: str) -> InventoryDocumentType | None:
        return self._session.scalar(
            select(InventoryDocumentType).where(
                InventoryDocumentType.company_id == company_id,
                InventoryDocumentType.code == code,
            )
        )

    def add(self, doc_type: InventoryDocumentType) -> InventoryDocumentType:
        self._session.add(doc_type)
        return doc_type

    def save(self, doc_type: InventoryDocumentType) -> InventoryDocumentType:
        self._session.add(doc_type)
        return doc_type

    def code_exists(
        self, company_id: int, code: str, exclude_id: int | None = None
    ) -> bool:
        predicate = (InventoryDocumentType.company_id == company_id) & (
            InventoryDocumentType.code == code
        )
        if exclude_id is not None:
            predicate = predicate & (InventoryDocumentType.id != exclude_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
