from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class UnitOfMeasure(TimestampMixin, ActiveFlagMixin, Base):
    """Normalized unit-of-measure reference data, scoped to a company."""

    __tablename__ = "units_of_measure"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_units_of_measure_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("uom_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    ratio_to_base: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, server_default="1"
    )

    company: Mapped["Company"] = relationship("Company")
    category: Mapped["UomCategory | None"] = relationship(
        "UomCategory", back_populates="units"
    )
