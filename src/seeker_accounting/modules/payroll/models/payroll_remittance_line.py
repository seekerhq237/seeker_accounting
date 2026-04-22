from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollRemittanceLine(TimestampMixin, Base):
    """Detail line within a payroll remittance batch.

    Each line represents one statutory component being remitted
    (e.g. IRPP, CNPS employee, CNPS employer, TDL, CAC, FNE).
    Lines are traceable to posted payroll liabilities through
    payroll_component_id → liability_account_id on the component.

    status_code lifecycle (service-enforced):
        open → partial → paid
        open or partial → cancelled
    """

    __tablename__ = "payroll_remittance_lines"
    __table_args__ = (
        UniqueConstraint("payroll_remittance_batch_id", "line_number"),
        Index(
            "ix_payroll_remittance_lines_batch_id",
            "payroll_remittance_batch_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payroll_remittance_batch_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_remittance_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    payroll_component_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_components.id", ondelete="RESTRICT"),
        nullable=True,
    )
    liability_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    batch: Mapped["PayrollRemittanceBatch"] = relationship(
        "PayrollRemittanceBatch", back_populates="lines"
    )
    payroll_component: Mapped["PayrollComponent | None"] = relationship("PayrollComponent")
    liability_account: Mapped["Account | None"] = relationship("Account")
