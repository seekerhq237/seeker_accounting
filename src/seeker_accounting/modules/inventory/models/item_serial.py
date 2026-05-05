from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


SERIAL_STATUS_CODES: frozenset[str] = frozenset(
    {"allocated", "in_stock", "in_transit", "issued", "returned", "scrapped", "warranty_expired"}
)


class ItemSerial(TimestampMixin, Base):
    """Single serialized inventory object with current lifecycle state."""

    __tablename__ = "item_serials"
    __table_args__ = (
        UniqueConstraint("company_id", "item_id", "serial_number", name="uq_item_serials_company_item_serial"),
        Index("ix_item_serials_company_item", "company_id", "item_id"),
        Index("ix_item_serials_status_code", "status_code"),
        Index("ix_item_serials_current_location_id", "current_location_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    batch_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("item_batches.id", ondelete="RESTRICT"), nullable=True
    )
    serial_number: Mapped[str] = mapped_column(String(100), nullable=False)
    status_code: Mapped[str] = mapped_column(
        String(30), nullable=False, default="allocated", server_default="allocated"
    )
    current_location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True
    )
    current_doc_line_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"), nullable=True
    )
    warranty_until: Mapped[date | None] = mapped_column(Date(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item", back_populates="serials")
    batch: Mapped["ItemBatch | None"] = relationship("ItemBatch")
    current_location: Mapped["InventoryLocation | None"] = relationship("InventoryLocation")
    current_doc_line: Mapped["InventoryDocumentLine | None"] = relationship(
        "InventoryDocumentLine", foreign_keys=[current_doc_line_id]
    )
    document_line_links: Mapped[list["InventoryDocumentLineSerial"]] = relationship(
        "InventoryDocumentLineSerial", back_populates="serial"
    )
