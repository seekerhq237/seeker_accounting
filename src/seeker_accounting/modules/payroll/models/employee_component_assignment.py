from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class EmployeeComponentAssignment(TimestampMixin, ActiveFlagMixin, Base):
    """Links an employee to a recurring payroll component with optional overrides.

    If override_amount is set, it replaces the component's fixed calculation.
    If override_rate is set (decimal, e.g. 0.30 for 30%), it overrides the
    component's configured percentage rate.

    Effective-dated: the engine uses the assignment whose range covers the
    pay period.
    """

    __tablename__ = "employee_component_assignments"
    __table_args__ = (
        UniqueConstraint("company_id", "employee_id", "component_id", "effective_from"),
        Index("ix_emp_comp_assignments_company_id", "company_id"),
        Index("ix_emp_comp_assignments_employee_id", "employee_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
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
    override_amount: Mapped[object | None] = mapped_column(Numeric(18, 4), nullable=True)
    override_rate: Mapped[object | None] = mapped_column(Numeric(12, 6), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date(), nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date(), nullable=True)

    employee: Mapped["Employee"] = relationship("Employee")
    component: Mapped["PayrollComponent"] = relationship("PayrollComponent")
