"""Tax obligation model.

Represents a single statutory tax-filing obligation for a company in
a specific period (e.g. "VAT for March 2026" due 2026-04-15).

Obligations are generated from ``CompanyTaxProfile`` (which tax types
the company is subject to) plus a calendar generator. They are the
operational anchor that links a *period* of accounting activity to the
*return* document and the *payment* that ultimately settles it.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class TaxObligation(TimestampMixin, Base):
    __tablename__ = "tax_obligations"
    __table_args__ = (
        Index("ix_tax_obligations_company_id", "company_id"),
        Index(
            "ix_tax_obligations_company_period",
            "company_id",
            "tax_type_code",
            "period_start",
            "period_end",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tax_type_code: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end: Mapped[date] = mapped_column(Date(), nullable=False)
    due_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    tax_returns: Mapped[list["TaxReturn"]] = relationship(
        "TaxReturn",
        back_populates="obligation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<TaxObligation company_id={self.company_id} "
            f"type={self.tax_type_code} period={self.period_start}..{self.period_end} "
            f"status={self.status_code}>"
        )
