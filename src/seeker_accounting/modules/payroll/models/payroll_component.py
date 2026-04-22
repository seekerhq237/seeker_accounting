from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class PayrollComponent(TimestampMixin, ActiveFlagMixin, Base):
    """A configurable earning, deduction, or contribution line for payroll.

    component_type_code values (enforced in service, not DB):
        earning, deduction, employer_contribution, tax, informational

    calculation_method_code values (enforced in service):
        fixed_amount, percentage, rule_based, manual_input, hourly
    """

    __tablename__ = "payroll_components"
    __table_args__ = (
        UniqueConstraint("company_id", "component_code"),
        Index("ix_payroll_components_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    component_code: Mapped[str] = mapped_column(String(30), nullable=False)
    component_name: Mapped[str] = mapped_column(String(100), nullable=False)
    component_type_code: Mapped[str] = mapped_column(String(30), nullable=False)
    calculation_method_code: Mapped[str] = mapped_column(String(30), nullable=False)
    is_taxable: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=expression.false()
    )
    is_pensionable: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, default=False, server_default=expression.false()
    )
    expense_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    liability_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )

    expense_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[expense_account_id]
    )
    liability_account: Mapped["Account | None"] = relationship(
        "Account", foreign_keys=[liability_account_id]
    )
