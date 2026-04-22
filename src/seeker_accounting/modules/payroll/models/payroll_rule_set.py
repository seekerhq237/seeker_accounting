from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import ActiveFlagMixin, Base, TimestampMixin


class PayrollRuleSet(TimestampMixin, ActiveFlagMixin, Base):
    """Effective-dated rule set for a statutory or company payroll rule.

    rule_type_code values (enforced in service):
        pit, pension_employee, pension_employer, accident_risk,
        overtime, levy, other

    calculation_basis_code values (enforced in service):
        gross_salary, basic_salary, taxable_gross, pensionable_gross,
        fixed, other
    """

    __tablename__ = "payroll_rule_sets"
    __table_args__ = (
        UniqueConstraint("company_id", "rule_code", "effective_from"),
        Index("ix_payroll_rule_sets_company_id", "company_id"),
        Index("ix_payroll_rule_sets_rule_code", "company_id", "rule_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_code: Mapped[str] = mapped_column(String(30), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type_code: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date(), nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date(), nullable=True)
    calculation_basis_code: Mapped[str] = mapped_column(String(30), nullable=False)

    brackets: Mapped[list["PayrollRuleBracket"]] = relationship(
        "PayrollRuleBracket",
        back_populates="rule_set",
        order_by="PayrollRuleBracket.line_number",
        cascade="all, delete-orphan",
    )
