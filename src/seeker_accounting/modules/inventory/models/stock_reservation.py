"""Stock reservation records.

Per ``docs/inventory_upgrade_plan.md`` Slice 2.4: sales orders, jobs, and
projects can reserve stock against ``(item, location)``. Reservations consume
"available" quantity without touching the immutable stock ledger.

Lifecycle:
    pending  →  fulfilled  (when the related issue document is posted)
    pending  →  cancelled  (when the originating order/job is cancelled)
    pending  →  expired    (when ``expires_at`` passes without fulfilment)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class StockReservation(Base):
    """Pending stock reservation for a future issue."""

    __tablename__ = "stock_reservations"
    __table_args__ = (
        Index("ix_stock_reservations_company_item_location", "company_id", "item_id", "location_id"),
        Index("ix_stock_reservations_source", "company_id", "source_module", "source_document_id"),
        Index("ix_stock_reservations_status_code", "company_id", "status_code"),
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
    location_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    source_module: Mapped[str] = mapped_column(String(40), nullable=False)
    source_document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_document_line_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    company: Mapped["Company"] = relationship("Company")
    item: Mapped["Item"] = relationship("Item")
    location: Mapped["InventoryLocation | None"] = relationship("InventoryLocation")
