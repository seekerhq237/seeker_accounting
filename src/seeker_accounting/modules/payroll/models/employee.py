from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class Employee(TimestampMixin, ActiveFlagMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("company_id", "employee_number"),
        Index("ix_employees_company_id", "company_id"),
        Index("ix_employees_department_id", "department_id"),
        Index("ix_employees_position_id", "position_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    employee_number: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    department_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    position_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("positions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    hire_date: Mapped[date] = mapped_column(Date(), nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cnps_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    default_payment_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("financial_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    base_currency_code: Mapped[str] = mapped_column(
        String(3),
        ForeignKey("currencies.code", ondelete="RESTRICT"),
        nullable=False,
    )

    department: Mapped["Department | None"] = relationship("Department")
    position: Mapped["Position | None"] = relationship("Position")
