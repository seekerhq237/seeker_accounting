from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class InventoryDocumentLineSerial(Base):
    """Association between an inventory document line and a named serial."""

    __tablename__ = "inventory_document_line_serials"
    __table_args__ = (
        Index("ix_inv_doc_line_serials_doc_line_id", "inventory_document_line_id"),
        Index("ix_inv_doc_line_serials_serial_id", "serial_id"),
    )

    inventory_document_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_document_lines.id", ondelete="CASCADE"),
        primary_key=True,
    )
    serial_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("item_serials.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="movement", server_default="movement"
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    document_line: Mapped["InventoryDocumentLine"] = relationship(
        "InventoryDocumentLine", back_populates="serial_links"
    )
    serial: Mapped["ItemSerial"] = relationship("ItemSerial", back_populates="document_line_links")
