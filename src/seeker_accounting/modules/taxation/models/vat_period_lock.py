"""Model for VAT period locks (T43).

A VatPeriodLock row prevents new postings whose ``tax_point_date`` falls
within the locked period for the given tax type.  A row is created
automatically when a return is filed; it can be removed by a user
with the ``taxation.periods.unlock`` permission.
"""
from __future__ import annotations

import datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base, TimestampMixin

TAX_TYPE_VAT = "VAT"


class VatPeriodLock(TimestampMixin, Base):
    __tablename__ = "vat_period_locks"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_start", "period_end", "tax_type_code",
            name="uq_vat_period_locks_company_period_type",
        ),
        Index("ix_vat_period_locks_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[datetime.date] = mapped_column(Date(), nullable=False)
    period_end: Mapped[datetime.date] = mapped_column(Date(), nullable=False)
    tax_type_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TAX_TYPE_VAT
    )
    locked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(), nullable=False
    )
    locked_by_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    return_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_returns.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
