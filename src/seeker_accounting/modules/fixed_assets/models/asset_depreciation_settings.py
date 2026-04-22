from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from decimal import Decimal

from seeker_accounting.db.base import Base, TimestampMixin


class AssetDepreciationSettings(TimestampMixin, Base):
    """Method-specific depreciation parameters per asset.

    One row per asset (0..1 relationship). Only needs to exist when the chosen
    depreciation method requires parameters beyond the asset's core fields.

    Relevant fields by method:
        declining_balance / double_declining_balance / declining_balance_150
            declining_factor         — 1.0, 1.5, or 2.0
            switch_to_straight_line  — switch to SL when SL > DB (optional)

        units_of_production
            expected_total_units     — total estimated units over asset life

        depletion
            expected_total_units     — total recoverable resource units

        annuity / sinking_fund
            interest_rate            — periodic (monthly) interest rate, e.g. 0.005 = 0.5%

        macrs
            macrs_profile_id         — FK to macrs_profiles seeded table
            macrs_convention_code    — half_year | mid_quarter | mid_month
    """

    __tablename__ = "asset_depreciation_settings"
    __table_args__ = (
        UniqueConstraint("asset_id"),
        Index("ix_asset_depreciation_settings_company_id", "company_id"),
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

    # Declining-balance family
    declining_factor: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    switch_to_straight_line: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False
    )

    # Units of production / depletion
    expected_total_units: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    # Annuity / sinking fund
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 8), nullable=True)

    # MACRS
    macrs_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("macrs_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    macrs_convention_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="depreciation_settings")
    macrs_profile: Mapped["MacrsProfile | None"] = relationship("MacrsProfile")
