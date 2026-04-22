from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class EmployeeCompensationProfile(TimestampMixin, ActiveFlagMixin, Base):
    """Base salary and contract parameters for an employee at a point in time.

    One active profile per employee determines their gross/basic salary
    used as the calculation base for the payroll run engines.

    Effective-dated: multiple profiles per employee allowed but only the
    profile whose effective_from <= pay_period <= effective_to is used.
    """

    __tablename__ = "employee_compensation_profiles"
    __table_args__ = (
        UniqueConstraint("company_id", "employee_id", "effective_from"),
        Index("ix_emp_comp_profiles_company_id", "company_id"),
        Index("ix_emp_comp_profiles_employee_id", "employee_id"),
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
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)
    basic_salary: Mapped[object] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(Date(), nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date(), nullable=True)
    number_of_parts: Mapped[object] = mapped_column(
        Numeric(3, 1), nullable=False, server_default="1.0",
        comment="Quotient familial — IRPP family parts (1.0 = single, 2.0 = married, etc.)",
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    employee: Mapped["Employee"] = relationship("Employee")
