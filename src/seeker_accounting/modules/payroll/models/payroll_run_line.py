from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollRunLine(TimestampMixin, Base):
    """Individual component calculation line for an employee within a payroll run.

    component_type_code mirrors the component's type:
        earning, deduction, employer_contribution, tax, informational
    """

    __tablename__ = "payroll_run_lines"
    __table_args__ = (
        Index("ix_payroll_run_lines_run_id", "run_id"),
        Index("ix_payroll_run_lines_run_employee_id", "run_employee_id"),
        Index("ix_payroll_run_lines_employee_id", "employee_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_employee_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_run_employees.id", ondelete="CASCADE"),
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
    component_type_code: Mapped[str] = mapped_column(String(30), nullable=False)
    calculation_basis: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    rate_applied: Mapped[object | None] = mapped_column(Numeric(12, 6), nullable=True)
    component_amount: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    run_employee: Mapped["PayrollRunEmployee"] = relationship(
        "PayrollRunEmployee", back_populates="lines"
    )
    component: Mapped["PayrollComponent"] = relationship("PayrollComponent")
