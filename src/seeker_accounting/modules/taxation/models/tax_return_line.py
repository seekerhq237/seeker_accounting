"""Tax return line — one statutory box value on a return."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String
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
    # Slice T30: DGI VAT-return lines have separate "Base HT" and "VAT
    # amount" columns (L17, L26–L29).  Pure-base lines (L21, L22) carry
    # the base in ``base_amount`` with ``amount = 0``.  Computed total
    # lines (L23, L30, L36, L37, L40, L43, L47) leave ``base_amount``
    # NULL.  Older returns drafted before T30 have ``base_amount = NULL``
    # everywhere — the form layout falls back to the legacy bridge.
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Slice T49: set to True when the parent return is filed.  Guards
    # against accidental line mutation after the return is immutable.
    is_immutable: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False
    )

    tax_return: Mapped["TaxReturn"] = relationship("TaxReturn", back_populates="lines")
