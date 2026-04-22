from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base


class AssetDepreciationRunLine(Base):
    """One line in a depreciation run — one entry per eligible asset."""

    __tablename__ = "asset_depreciation_run_lines"
    __table_args__ = (
        Index("ix_asset_depreciation_run_lines_run_id", "asset_depreciation_run_id"),
        Index("ix_asset_depreciation_run_lines_asset_id", "asset_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_depreciation_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("asset_depreciation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    depreciation_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    accumulated_depreciation_after: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    net_book_value_after: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    depreciation_run: Mapped["AssetDepreciationRun"] = relationship(
        "AssetDepreciationRun", back_populates="lines"
    )
    asset: Mapped["Asset"] = relationship("Asset", back_populates="depreciation_run_lines")
