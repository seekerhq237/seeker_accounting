"""Item-supplier catalog (P2 / Slice 3.4).

Tracks which suppliers can supply each item, with the preferred supplier flag,
last known cost, lead time, and UoM.  Auto-updated by the GoodsReceiptService
whenever a goods-receipt-purchase is posted.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.inventory.models.item import Item
    from seeker_accounting.modules.inventory.models.unit_of_measure import UnitOfMeasure
    from seeker_accounting.modules.suppliers.models.supplier import Supplier


class ItemSupplier(TimestampMixin, Base):
    """Per-(company, item, supplier) sourcing relationship."""

    __tablename__ = "item_suppliers"
    __table_args__ = (
        UniqueConstraint("company_id", "item_id", "supplier_id", name="uq_item_suppliers"),
        Index("ix_item_suppliers_company_item", "company_id", "item_id"),
        Index("ix_item_suppliers_company_supplier", "company_id", "supplier_id"),
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
    supplier_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_item_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    supplier_uom_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("units_of_measure.id", ondelete="RESTRICT"),
        nullable=True,
    )
    last_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    last_currency_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_purchase_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_preferred: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    minimum_order_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    item: Mapped["Item"] = relationship("Item", foreign_keys=[item_id])
    supplier: Mapped["Supplier"] = relationship("Supplier", foreign_keys=[supplier_id])
    supplier_uom: Mapped["UnitOfMeasure | None"] = relationship(
        "UnitOfMeasure", foreign_keys=[supplier_uom_id]
    )
