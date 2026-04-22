from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, TimestampMixin


class FiscalPeriod(TimestampMixin, Base):
    __tablename__ = "fiscal_periods"
    __table_args__ = (
        CheckConstraint("period_number >= 1", name="period_number_positive"),
        UniqueConstraint("company_id", "fiscal_year_id", "period_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fiscal_year_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fiscal_years.id", ondelete="RESTRICT"),
        nullable=False,
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    period_code: Mapped[str] = mapped_column(String(30), nullable=False)
    period_name: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[date] = mapped_column(Date(), nullable=False)
    end_date: Mapped[date] = mapped_column(Date(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_adjustment_period: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )

    company: Mapped["Company"] = relationship("Company")
    fiscal_year: Mapped["FiscalYear"] = relationship("FiscalYear", back_populates="periods")
    journal_entries: Mapped[list["JournalEntry"]] = relationship(
        "JournalEntry",
        back_populates="fiscal_period",
    )
