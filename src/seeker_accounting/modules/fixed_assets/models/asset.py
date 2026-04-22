from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class Asset(TimestampMixin, Base):
    """Fixed asset register entry.

    Status lifecycle: draft -> active -> fully_depreciated | disposed
    Depreciation method codes: see DepreciationMethod catalog (depreciation_methods table).
    """

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("company_id", "asset_number"),
        Index("ix_assets_company_id", "company_id"),
        Index("ix_assets_company_id_status_code", "company_id", "status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    asset_number: Mapped[str] = mapped_column(String(40), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(150), nullable=False)

    asset_category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("asset_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )

    acquisition_date: Mapped[date] = mapped_column(Date(), nullable=False)
    capitalization_date: Mapped[date] = mapped_column(Date(), nullable=False)
    acquisition_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    salvage_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Asset-level depreciation settings (override category defaults where needed)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    depreciation_method_code: Mapped[str] = mapped_column(String(30), nullable=False)

    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    supplier_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=True,
    )
    purchase_bill_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("purchase_bills.id", ondelete="RESTRICT"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    category: Mapped["AssetCategory"] = relationship("AssetCategory", back_populates="assets")
    supplier: Mapped["Supplier | None"] = relationship("Supplier")
    depreciation_run_lines: Mapped[list["AssetDepreciationRunLine"]] = relationship(
        "AssetDepreciationRunLine", back_populates="asset"
    )
    depreciation_settings: Mapped["AssetDepreciationSettings | None"] = relationship(
        "AssetDepreciationSettings", back_populates="asset", uselist=False
    )
    components: Mapped[list["AssetComponent"]] = relationship(
        "AssetComponent", back_populates="parent_asset"
    )
    usage_records: Mapped[list["AssetUsageRecord"]] = relationship(
        "AssetUsageRecord", back_populates="asset"
    )
    pool_memberships: Mapped[list["AssetDepreciationPoolMember"]] = relationship(
        "AssetDepreciationPoolMember", back_populates="asset"
    )
    depletion_profile: Mapped["AssetDepletionProfile | None"] = relationship(
        "AssetDepletionProfile", back_populates="asset", uselist=False
    )
