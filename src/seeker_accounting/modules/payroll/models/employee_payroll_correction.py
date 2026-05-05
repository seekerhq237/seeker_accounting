from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class EmployeePayrollCorrection(TimestampMixin, Base):
    """Additive payroll correction fact applied by a later run calculation."""

    __tablename__ = "employee_payroll_corrections"
    __table_args__ = (
        Index("ix_employee_payroll_corrections_company_period", "company_id", "period_year", "period_month"),
        Index("ix_employee_payroll_corrections_employee", "employee_id"),
        Index("ix_employee_payroll_corrections_status", "status_code"),
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
    period_year: Mapped[int] = mapped_column(Integer(), nullable=False)
    period_month: Mapped[int] = mapped_column(Integer(), nullable=False)
    correction_amount: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_run_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_run_employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    employee: Mapped["Employee"] = relationship("Employee")
    component: Mapped["PayrollComponent"] = relationship("PayrollComponent")
