"""VAT Capital Goods Register.

Tracks assets subject to multi-year VAT input-tax adjustment under
OHADA / Cameroon DGI capital-goods rules.  Each asset is monitored
for a statutory number of years (default 5).  Annual adjustments are
recorded via PostedTaxLine facts; this table holds the permanent
registration record and disposal flag.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class VatCapitalGood(TimestampMixin, Base):
    """One row per capital asset registered in the VAT capital-goods scheme."""

    __tablename__ = "vat_capital_goods_register"
    __table_args__ = (
        Index("ix_vat_cg_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Nullable FK to fixed_assets.id — module not yet built.
    fixed_asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    asset_description: Mapped[str] = mapped_column(String(200), nullable=False)
    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Amount excluding VAT on which input-tax was initially claimed.
    base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # VAT amount initially recovered at acquisition.
    vat_recovered_initial: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("0.00")
    )

    # Number of years the asset must be monitored (DGI default: 5).
    monitored_years: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # ACTIVE | DISPOSED
    status_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE"
    )

    disposal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship("Company")
