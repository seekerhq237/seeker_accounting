from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base


class AssetDepreciationPoolMember(Base):
    """Membership record linking an asset to a depreciation pool.

    An asset may only belong to one active pool at a time.
    left_date being NULL means the asset is currently a member.
    """

    __tablename__ = "asset_depreciation_pool_members"
    __table_args__ = (
        UniqueConstraint("pool_id", "asset_id"),
        Index("ix_asset_depr_pool_members_pool_id", "pool_id"),
        Index("ix_asset_depr_pool_members_asset_id", "asset_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pool_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("asset_depreciation_pools.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    joined_date: Mapped[date] = mapped_column(Date(), nullable=False)
    left_date: Mapped[date | None] = mapped_column(Date(), nullable=True)

    pool: Mapped["AssetDepreciationPool"] = relationship(
        "AssetDepreciationPool", back_populates="members"
    )
    asset: Mapped["Asset"] = relationship("Asset", back_populates="pool_memberships")
