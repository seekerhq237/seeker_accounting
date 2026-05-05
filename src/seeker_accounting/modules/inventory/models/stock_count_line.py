from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class StockCountLine(Base):
    """Frozen snapshot and entered count for one item/location pair."""

    __tablename__ = "stock_count_lines"
    __table_args__ = (
        UniqueConstraint("session_id", "item_id", "location_id", name="uq_stock_count_lines_session_item_location"),
        Index("ix_stock_count_lines_session_id", "session_id"),
        Index("ix_stock_count_lines_item_location", "item_id", "location_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_count_sessions.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=True
    )
    snapshot_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    snapshot_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    counted_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    variance_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    variance_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    variance_reason_code_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_reason_codes.id", ondelete="RESTRICT"), nullable=True
    )
    counted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    counted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)

    session: Mapped["StockCountSession"] = relationship("StockCountSession", back_populates="lines")
    item: Mapped["Item"] = relationship("Item")
    location: Mapped["InventoryLocation | None"] = relationship("InventoryLocation")
    variance_reason_code: Mapped["InventoryReasonCode | None"] = relationship("InventoryReasonCode")
    counted_by_user: Mapped["User | None"] = relationship("User")
    recounts: Mapped[list["StockCountRecount"]] = relationship(
        "StockCountRecount", back_populates="line", cascade="all, delete-orphan"
    )


class StockCountRecount(Base):
    """Append-only recount fact for a stock count line."""

    __tablename__ = "stock_count_recounts"
    __table_args__ = (Index("ix_stock_count_recounts_line_id", "line_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_count_lines.id", ondelete="CASCADE"), nullable=False
    )
    recount_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    recounted_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    recounted_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    line: Mapped["StockCountLine"] = relationship("StockCountLine", back_populates="recounts")
    recounted_by_user: Mapped["User | None"] = relationship("User")
