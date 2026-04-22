from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollRemittanceBatch(TimestampMixin, Base):
    """Statutory remittance tracking header for DGI, CNPS, or other authorities.

    This is a settlement-fact header, not a posting truth table.  Accounting
    truth for statutory liabilities comes from the posted payroll journal.
    amount_due / amount_paid are maintained by PayrollRemittanceService.

    remittance_authority_code allowed values (service-enforced):
        dgi, cnps, other

    status_code lifecycle (service-enforced):
        draft → open → partial → paid
        draft or open → cancelled
    """

    __tablename__ = "payroll_remittance_batches"
    __table_args__ = (
        UniqueConstraint("company_id", "batch_number"),
        Index("ix_payroll_remittance_batches_company_id", "company_id"),
        Index("ix_payroll_remittance_batches_payroll_run_id", "payroll_run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_number: Mapped[str] = mapped_column(String(30), nullable=False)
    payroll_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    period_start_date: Mapped[date] = mapped_column(Date(), nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date(), nullable=False)
    remittance_authority_code: Mapped[str] = mapped_column(String(30), nullable=False)
    remittance_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    treasury_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("treasury_transactions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    payroll_run: Mapped["PayrollRun | None"] = relationship("PayrollRun")
    lines: Mapped[list["PayrollRemittanceLine"]] = relationship(
        "PayrollRemittanceLine",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    created_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_user_id]
    )
    updated_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[updated_by_user_id]
    )
