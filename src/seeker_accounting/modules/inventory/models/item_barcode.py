"""Item barcode table (P6 / Slice 7.5).

An item can have multiple barcodes (EAN-13, EAN-8, Code128, QR, etc.).
The primary barcode is also mirrored as `items.barcode` for fast look-ups
without a join.

barcode_type_code choices: 'EAN13', 'EAN8', 'CODE128', 'CODE39', 'QR', 'UPC'
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.inventory.models.item import Item


class ItemBarcode(TimestampMixin, Base):
    """One barcode entry for an item."""

    __tablename__ = "item_barcodes"
    __table_args__ = (
        UniqueConstraint("company_id", "barcode", name="uq_item_barcodes_company_barcode"),
        Index("ix_item_barcodes_item_id", "item_id"),
        Index("ix_item_barcodes_barcode", "company_id", "barcode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    barcode: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode_type_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="EAN13"
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=expression.false()
    )

    item: Mapped["Item"] = relationship("Item", foreign_keys=[item_id])
