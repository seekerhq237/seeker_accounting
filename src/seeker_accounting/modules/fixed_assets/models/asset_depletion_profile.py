from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class AssetDepletionProfile(TimestampMixin, Base):
    """Depletion parameters for natural-resource assets.

    Used when depreciation_method_code = 'depletion'.
    One row per asset (enforced by UNIQUE on asset_id).

    Depletion per period = units_used_in_period * cost_per_unit
    where cost_per_unit = (acquisition_cost - salvage_value) / estimated_total_units.

    Usage records are stored in asset_usage_records.
    """

    __tablename__ = "asset_depletion_profiles"
    __table_args__ = (
        UniqueConstraint("asset_id"),
        Index("ix_asset_depletion_profiles_company_id", "company_id"),
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
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # oil | gas | timber | mineral | other
    estimated_total_units: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_description: Mapped[str] = mapped_column(String(50), nullable=False)  # barrels | tons | board-feet | etc.

    asset: Mapped["Asset"] = relationship("Asset", back_populates="depletion_profile")
