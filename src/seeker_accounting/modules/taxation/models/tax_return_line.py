"""Tax return line — one statutory box value on a return."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class TaxReturnLine(TimestampMixin, Base):
    __tablename__ = "tax_return_lines"
    __table_args__ = (
        Index("ix_tax_return_lines_return_id", "tax_return_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tax_return_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tax_returns.id", ondelete="CASCADE"),
        nullable=False,
    )
    box_code: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    tax_return: Mapped["TaxReturn"] = relationship("TaxReturn", back_populates="lines")
