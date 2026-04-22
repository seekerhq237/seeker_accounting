from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class CompanyFiscalDefault(Base):
    __tablename__ = "company_fiscal_defaults"

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_year_start_day: Mapped[int] = mapped_column(Integer, nullable=False)
    default_posting_grace_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="fiscal_defaults")

