"""Per-item UoM matrix with conversion direction, defaults and rounding rules.

Implements Slice 1.3 of the inventory upgrade plan. Where the legacy
:class:`~seeker_accounting.modules.inventory.models.unit_of_measure.UnitOfMeasure`
table provided a flat list of UoMs grouped by category, this table records, for
each individual item, the additional UoMs the item may be transacted in, the
rounding rule applied when converting transaction quantities to base quantity,
and which UoMs are the default for purchase and sales workflows.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ItemUomConversion(TimestampMixin, Base):
    """Allowed UoM, ratio, defaults, rounding rule for a single item."""

    __tablename__ = "item_uom_conversions"
    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "unit_of_measure_id",
            name="uq_item_uom_conversions_item_id_unit_of_measure_id",
        ),
        Index("ix_item_uom_conversions_item_id", "item_id"),
        Index("ix_item_uom_conversions_unit_of_measure_id", "unit_of_measure_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    unit_of_measure_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=False
    )
    ratio_to_base: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    """Multiplier applied to a transaction quantity expressed in this UoM to
    obtain the equivalent quantity in the item's base UoM. ``ratio_to_base``
    must be strictly positive."""
    rounding_rule_code: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    """One of ``up``, ``down``, ``nearest``, ``none``."""
    min_increment: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    """Optional minimum increment used by the rounding rule (e.g. 0.5 for half-cases)."""
    is_purchase_default: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_sales_default: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_stocking: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item", back_populates="uom_conversions")
    unit_of_measure: Mapped["UnitOfMeasure"] = relationship("UnitOfMeasure")
