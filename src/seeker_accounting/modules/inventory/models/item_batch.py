from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


BATCH_STATUS_CODES: frozenset[str] = frozenset({"active", "quarantined", "expired", "closed"})


class ItemBatch(TimestampMixin, Base):
    """Traceable batch or lot for batch-controlled inventory items."""

    __tablename__ = "item_batches"
    __table_args__ = (
        UniqueConstraint("company_id", "item_id", "batch_number", name="uq_item_batches_company_item_batch"),
        Index("ix_item_batches_company_item", "company_id", "item_id"),
        Index("ix_item_batches_expiry_on", "expiry_on"),
        Index("ix_item_batches_status_code", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    batch_number: Mapped[str] = mapped_column(String(80), nullable=False)
    manufactured_on: Mapped[date | None] = mapped_column(Date(), nullable=True)
    expiry_on: Mapped[date | None] = mapped_column(Date(), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True
    )
    status_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item", back_populates="batches")
    supplier: Mapped["Supplier | None"] = relationship("Supplier")
