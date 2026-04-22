from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollInputBatch(TimestampMixin, Base):
    """Batch of approved variable payroll inputs for a pay period.

    Variable inputs represent one-time or exceptional amounts for a period:
    bonuses, overtime hours, allowances not in the recurring profile, etc.

    status_code values (enforced in service):
        draft, approved, voided
    """

    __tablename__ = "payroll_input_batches"
    __table_args__ = (
        UniqueConstraint("company_id", "batch_reference"),
        Index("ix_payroll_input_batches_company_id", "company_id"),
        Index("ix_payroll_input_batches_period", "company_id", "period_year", "period_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_reference: Mapped[str] = mapped_column(String(30), nullable=False)
    period_year: Mapped[int] = mapped_column(Integer(), nullable=False)
    period_month: Mapped[int] = mapped_column(Integer(), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    lines: Mapped[list["PayrollInputLine"]] = relationship(
        "PayrollInputLine",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
