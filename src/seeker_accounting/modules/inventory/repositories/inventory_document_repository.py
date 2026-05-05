from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.inventory.models.inventory_document import InventoryDocument
from seeker_accounting.modules.inventory.models.inventory_document_line import InventoryDocumentLine
from seeker_accounting.modules.inventory.models.inventory_document_line_serial import (
    InventoryDocumentLineSerial,
)


class InventoryDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
        document_type_code: str | None = None,
    ) -> list[InventoryDocument]:
        stmt = select(InventoryDocument).where(InventoryDocument.company_id == company_id)
        if status_code is not None:
            stmt = stmt.where(InventoryDocument.status_code == status_code)
        if document_type_code is not None:
            stmt = stmt.where(InventoryDocument.document_type_code == document_type_code)
        stmt = stmt.order_by(InventoryDocument.document_date.desc(), InventoryDocument.id.desc())
        return list(self._session.scalars(stmt))

    def list_by_stock_count_session(
        self,
        company_id: int,
        stock_count_session_id: int,
    ) -> list[InventoryDocument]:
        stmt = (
            select(InventoryDocument)
            .where(
                InventoryDocument.company_id == company_id,
                InventoryDocument.stock_count_session_id == stock_count_session_id,
            )
            .order_by(InventoryDocument.document_date.asc(), InventoryDocument.id.asc())
        )
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, document_id: int) -> InventoryDocument | None:
        stmt = select(InventoryDocument).where(
            InventoryDocument.company_id == company_id,
            InventoryDocument.id == document_id,
        )
        return self._session.scalar(stmt)

    def get_detail(self, company_id: int, document_id: int) -> InventoryDocument | None:
        stmt = (
            select(InventoryDocument)
            .where(
                InventoryDocument.company_id == company_id,
                InventoryDocument.id == document_id,
            )
            .options(
                selectinload(InventoryDocument.lines).selectinload(InventoryDocumentLine.item),
                selectinload(InventoryDocument.lines).selectinload(InventoryDocumentLine.batch),
                selectinload(InventoryDocument.lines)
                .selectinload(InventoryDocumentLine.serial_links)
                .selectinload(InventoryDocumentLineSerial.serial),
            )
        )
        return self._session.scalar(stmt)

    def add(self, entity: InventoryDocument) -> InventoryDocument:
        self._session.add(entity)
        return entity

    def save(self, entity: InventoryDocument) -> InventoryDocument:
        self._session.add(entity)
        return entity
