from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base


class PayrollRuleBracket(Base):
    """One bracket/band line within a PayrollRuleSet.

    Supports progressive tax tables, CNPS bands, overtime multipliers, etc.
    No timestamps — brackets are owned/versioned through the parent rule set.
    """

    __tablename__ = "payroll_rule_brackets"
    __table_args__ = (
        UniqueConstraint("payroll_rule_set_id", "line_number"),
        Index("ix_payroll_rule_brackets_rule_set_id", "payroll_rule_set_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_rule_set_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("payroll_rule_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lower_bound_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    upper_bound_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    fixed_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    deduction_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cap_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    rule_set: Mapped["PayrollRuleSet"] = relationship("PayrollRuleSet", back_populates="brackets")
