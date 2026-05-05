from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class StockCountVariance(Base):
    """Approval audit fact for material stock count variances."""

    __tablename__ = "stock_count_variances"
    __table_args__ = (
        Index("ix_stock_count_variances_session_id", "session_id"),
        Index("ix_stock_count_variances_line_id", "line_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stock_count_sessions.id", ondelete="CASCADE"), nullable=False
    )
    line_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stock_count_lines.id", ondelete="CASCADE"), nullable=True
    )
    decision_code: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("inventory_reason_codes.id", ondelete="RESTRICT"), nullable=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    session: Mapped["StockCountSession"] = relationship("StockCountSession")
    line: Mapped["StockCountLine | None"] = relationship("StockCountLine")
    reason_code: Mapped["InventoryReasonCode | None"] = relationship("InventoryReasonCode")
    approved_by_user: Mapped["User | None"] = relationship("User")
