from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base


class MacrsProfile(Base):
    """Seeded MACRS GDS (General Depreciation System) rate tables.

    Global reference table — no company_id scoping.
    gds_rates_json stores a JSON array of annual percentage rates (as floats, e.g. 33.33).
    The schedule service applies these rates to the unadjusted cost basis (no salvage reduction).
    Annual rates are applied proportionally across 12 months within each year.

    Supported GDS classes (personal property, half-year convention):
        3-year, 5-year, 7-year, 10-year, 15-year, 20-year

    convention_code values: half_year | mid_quarter | mid_month
    """

    __tablename__ = "macrs_profiles"
    __table_args__ = (UniqueConstraint("class_code", "convention_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_code: Mapped[str] = mapped_column(String(20), nullable=False)
    class_name: Mapped[str] = mapped_column(String(100), nullable=False)
    recovery_period_years: Mapped[int] = mapped_column(Integer, nullable=False)
    convention_code: Mapped[str] = mapped_column(String(20), nullable=False)
    gds_rates_json: Mapped[str] = mapped_column(Text(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
