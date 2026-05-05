from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base


class BomComponent(Base):
    """Component line of a bill of material."""

    __tablename__ = "bom_components"
    __table_args__ = (
        UniqueConstraint("bom_id", "sequence", name="uq_bom_components_bom_sequence"),
        Index("ix_bom_components_bom_id", "bom_id"),
        Index("ix_bom_components_component_item_id", "component_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills_of_material.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    component_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_per: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    scrap_percent: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False, default=Decimal("0"))
    uom_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    bom: Mapped["BillOfMaterial"] = relationship("BillOfMaterial", back_populates="components")
    component_item: Mapped["Item"] = relationship("Item")
    uom: Mapped["UnitOfMeasure | None"] = relationship("UnitOfMeasure")
