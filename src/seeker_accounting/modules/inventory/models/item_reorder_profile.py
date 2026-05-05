"""Item reorder profiles (P6 / Slice 7.2).

Stores min/max/safety-stock quantities per (company, item, location).
The ReorderPlanningService uses these to generate purchase suggestions.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.inventory.models.item import Item
    from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation
    from seeker_accounting.modules.suppliers.models.supplier import Supplier


class ItemReorderProfile(TimestampMixin, Base):
    """Reorder parameters for an item, optionally scoped to a warehouse location."""

    __tablename__ = "item_reorder_profiles"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "item_id",
            "location_id",
            name="uq_reorder_profiles_item_location",
        ),
        Index("ix_reorder_profiles_company_item", "company_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True
    )
    min_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    max_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    safety_stock_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, default=Decimal("0")
    )
    lead_time_override_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_supplier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True
    )

    item: Mapped["Item"] = relationship("Item", foreign_keys=[item_id])
    location: Mapped["InventoryLocation | None"] = relationship(
        "InventoryLocation", foreign_keys=[location_id]
    )
    preferred_supplier: Mapped["Supplier | None"] = relationship(
        "Supplier", foreign_keys=[preferred_supplier_id]
    )
