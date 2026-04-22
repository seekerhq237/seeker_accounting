from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class AssetDepreciationPool(TimestampMixin, Base):
    """Group or composite depreciation pool.

    pool_type_code values:
        group     — assets of the same kind, same useful life; pool has a single rate
        composite — assets of different kinds and lives; pool uses a composite rate

    For group/composite methods, the pool carries a single depreciation method and
    life setting.  Individual assets in the pool do not maintain separate schedules;
    depreciation is computed on the pool's total cost basis.
    """

    __tablename__ = "asset_depreciation_pools"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_asset_depreciation_pools_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    pool_type_code: Mapped[str] = mapped_column(String(20), nullable=False)  # group | composite
    depreciation_method_code: Mapped[str] = mapped_column(String(30), nullable=False)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    members: Mapped[list["AssetDepreciationPoolMember"]] = relationship(
        "AssetDepreciationPoolMember", back_populates="pool"
    )
