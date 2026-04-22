from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class UomCategory(TimestampMixin, ActiveFlagMixin, Base):
    """Groups related units of measure that are inter-convertible."""

    __tablename__ = "uom_categories"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        Index("ix_uom_categories_company_id", "company_id"),
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

    company: Mapped["Company"] = relationship("Company")
    units: Mapped[list["UnitOfMeasure"]] = relationship(
        "UnitOfMeasure", back_populates="category"
    )
