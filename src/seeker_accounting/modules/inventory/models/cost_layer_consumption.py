"""Immutable cost-layer consumption records.

Per ``docs/inventory_upgrade_plan.md`` Slice 2.2: every time stock is issued
the engine creates a ``CostLayerConsumption`` row that documents exactly which
source layer was partially or fully consumed, by how much, and at what value.
This enables:

* Full audit trail of FIFO consumption order.
* Reconstruction of cost-of-goods for any historical issue.
* Future reversal workflows that can un-consume layers rather than guessing.

These rows are **append-only** — no UPDATE or DELETE is permitted by the
service layer.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class CostLayerConsumption(Base):
    """Single immutable consumption fact against one cost layer."""

    __tablename__ = "cost_layer_consumptions"
    __table_args__ = (
        Index("ix_cost_layer_consumptions_source_layer_id", "source_layer_id"),
        Index("ix_cost_layer_consumptions_consuming_doc_line_id", "consuming_doc_line_id"),
        Index("ix_cost_layer_consumptions_posting_date", "posting_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_layer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_cost_layers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    consuming_doc_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_document_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    consumed_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    consumed_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    posting_date: Mapped[date] = mapped_column(Date(), nullable=False)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    source_layer: Mapped["InventoryCostLayer"] = relationship("InventoryCostLayer")
    consuming_doc_line: Mapped["InventoryDocumentLine"] = relationship("InventoryDocumentLine")
