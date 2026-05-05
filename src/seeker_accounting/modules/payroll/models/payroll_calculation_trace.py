from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PayrollCalculationTrace(TimestampMixin, Base):
    """Persisted explanation step for a payroll run employee calculation."""

    __tablename__ = "payroll_calculation_traces"
    __table_args__ = (
        Index("ix_payroll_calculation_traces_run", "run_id"),
        Index("ix_payroll_calculation_traces_run_employee", "run_employee_id"),
        Index("ix_payroll_calculation_traces_employee", "employee_id"),
        Index("ix_payroll_calculation_traces_component", "component_id"),
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
    sequence_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    stage_code: Mapped[str] = mapped_column(String(60), nullable=False)
    component_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_components.id", ondelete="SET NULL"),
        nullable=True,
    )
    formula_code: Mapped[str] = mapped_column(String(100), nullable=False)
    input_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    amount: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    run_employee: Mapped["PayrollRunEmployee"] = relationship("PayrollRunEmployee")
    component: Mapped["PayrollComponent | None"] = relationship("PayrollComponent")
