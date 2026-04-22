from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollInputLine(TimestampMixin, Base):
    """One variable input entry within a payroll input batch.

    input_amount: monetary amount for the component (e.g. bonus amount).
    input_quantity: optional quantity for rate-based components (e.g. overtime hours).
    """

    __tablename__ = "payroll_input_lines"
    __table_args__ = (
        Index("ix_payroll_input_lines_batch_id", "batch_id"),
        Index("ix_payroll_input_lines_employee_id", "employee_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_input_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    component_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_components.id", ondelete="RESTRICT"),
        nullable=False,
    )
    input_amount: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False)
    input_quantity: Mapped[object | None] = mapped_column(Numeric(12, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(200), nullable=True)

    batch: Mapped["PayrollInputBatch"] = relationship("PayrollInputBatch", back_populates="lines")
    employee: Mapped["Employee"] = relationship("Employee")
    component: Mapped["PayrollComponent"] = relationship("PayrollComponent")
