from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.payroll.models.employee import Employee
    from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
    from seeker_accounting.modules.payroll.models.payroll_run_employee_project_allocation import (
        PayrollRunEmployeeProjectAllocation,
    )
    from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine


class PayrollRunEmployee(TimestampMixin, Base):
    """Employee-level summary for one payroll run.

    The six preserved payroll bases:
        gross_earnings         – sum of all earning lines (salary + allowances + overtime + BIK)
        taxable_salary_base    – gross used as the IRPP progressive-tax base
        tdl_base               – base for the TDL (local development tax)
        cnps_contributory_base – base for CNPS employee + employer pension contributions
        employer_cost_base     – total cost to employer: gross + all employer contributions
        net_payable            – gross_earnings minus all employee deductions and taxes

    status_code values (enforced in service):
        included   – employee processed normally
        excluded   – employee manually excluded from this run
        error      – calculation failed; see calculation_notes
    """

    __tablename__ = "payroll_run_employees"
    __table_args__ = (
        UniqueConstraint("company_id", "run_id", "employee_id"),
        Index("ix_payroll_run_employees_run_id", "run_id"),
        Index("ix_payroll_run_employees_employee_id", "employee_id"),
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
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # The six preserved payroll bases
    gross_earnings: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    taxable_salary_base: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    tdl_base: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    cnps_contributory_base: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    employer_cost_base: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    net_payable: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    # Aggregated summary totals
    total_earnings: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_employee_deductions: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_employer_contributions: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total_taxes: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="included")
    calculation_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Operator-supplied reason when status_code == "excluded" (set via
    # PayrollRunService.set_run_employee_inclusion). Not used for the "error"
    # status — errors go into calculation_notes.
    exclusion_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Payment settlement tracking (maintained by PayrollPaymentTrackingService)
    # unpaid / partial / paid — derived from payroll_payment_records aggregation
    payment_status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="unpaid")
    payment_date: Mapped[date | None] = mapped_column(Date(), nullable=True)

    run: Mapped["PayrollRun"] = relationship("PayrollRun", back_populates="employees")
    employee: Mapped["Employee"] = relationship("Employee")
    lines: Mapped[list["PayrollRunLine"]] = relationship(
        "PayrollRunLine",
        back_populates="run_employee",
        cascade="all, delete-orphan",
    )
    project_allocations: Mapped[list["PayrollRunEmployeeProjectAllocation"]] = relationship(
        "PayrollRunEmployeeProjectAllocation",
        back_populates="run_employee",
        cascade="all, delete-orphan",
    )
