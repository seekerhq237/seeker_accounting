from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class TreasuryTransactionLine(TimestampMixin, Base):
    __tablename__ = "treasury_transaction_lines"
    __table_args__ = (
        UniqueConstraint("treasury_transaction_id", "line_number"),
        Index("ix_treasury_transaction_lines_project_id", "project_id"),
        Index("ix_treasury_transaction_lines_project_job_id", "project_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    treasury_transaction_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("treasury_transactions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    party_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    party_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    contract_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_jobs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    project_cost_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_cost_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )

    treasury_transaction: Mapped["TreasuryTransaction"] = relationship(
        "TreasuryTransaction", back_populates="lines"
    )
    account: Mapped["Account"] = relationship("Account")
    tax_code: Mapped["TaxCode | None"] = relationship("TaxCode")
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
    project_cost_code: Mapped["ProjectCostCode | None"] = relationship("ProjectCostCode")
