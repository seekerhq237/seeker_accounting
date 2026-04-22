from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class AssetComponent(TimestampMixin, Base):
    """Child component of a parent asset using the 'component' depreciation method.

    When a parent asset uses depreciation_method_code = 'component', its total
    depreciation is the sum of depreciation computed independently for each active
    component.  Each component carries its own cost, salvage, life, and method.
    """

    __tablename__ = "asset_components"
    __table_args__ = (
        Index("ix_asset_components_parent_asset_id", "parent_asset_id"),
        Index("ix_asset_components_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_asset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    component_name: Mapped[str] = mapped_column(String(150), nullable=False)
    acquisition_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    salvage_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    depreciation_method_code: Mapped[str] = mapped_column(String(30), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    parent_asset: Mapped["Asset"] = relationship("Asset", back_populates="components")
