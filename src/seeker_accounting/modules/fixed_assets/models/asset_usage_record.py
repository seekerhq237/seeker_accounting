from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base


class AssetUsageRecord(Base):
    """Period-level usage record for units-of-production and depletion methods.

    Each row records actual units consumed/produced during a period.
    The depreciation amount for the period is:
        units_used * (depreciable_base / expected_total_units)

    usage_date should be the last day of the period the units were consumed.
    """

    __tablename__ = "asset_usage_records"
    __table_args__ = (
        Index("ix_asset_usage_records_asset_id", "asset_id"),
        Index("ix_asset_usage_records_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    asset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    usage_date: Mapped[date] = mapped_column(Date(), nullable=False)
    units_used: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="usage_records")
