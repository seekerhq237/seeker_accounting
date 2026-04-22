from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class InventoryCostLayer(Base):
    """Cost-layer facts for inventory valuation (weighted average / FIFO)."""

    __tablename__ = "inventory_cost_layers"
    __table_args__ = (
        Index("ix_inventory_cost_layers_company_id_item_id", "company_id", "item_id"),
        Index("ix_inventory_cost_layers_item_id", "item_id"),
        Index("ix_inventory_cost_layers_document_line_id", "inventory_document_line_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    inventory_document_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    layer_date: Mapped[date] = mapped_column(Date(), nullable=False)
    quantity_in: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    quantity_remaining: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item")
    inventory_document_line: Mapped["InventoryDocumentLine"] = relationship("InventoryDocumentLine")
