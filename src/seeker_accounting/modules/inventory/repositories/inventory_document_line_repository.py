from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine


class InventoryDocumentLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_document(self, document_id: int) -> list[InventoryDocumentLine]:
        stmt = (
            select(InventoryDocumentLine)
            .where(InventoryDocumentLine.inventory_document_id == document_id)
            .order_by(InventoryDocumentLine.line_number)
        )
        return list(self._session.scalars(stmt))

    def add(self, entity: InventoryDocumentLine) -> InventoryDocumentLine:
        self._session.add(entity)
        return entity

    def delete_for_document(self, document_id: int) -> None:
        lines = self.list_for_document(document_id)
        for line in lines:
            self._session.delete(line)
