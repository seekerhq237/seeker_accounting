from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class PurchaseBillLine(TimestampMixin, Base):
    __tablename__ = "purchase_bill_lines"
    __table_args__ = (
        UniqueConstraint("purchase_bill_id", "line_number"),
        Index("ix_purchase_bill_lines_project_id", "project_id"),
        Index("ix_purchase_bill_lines_project_job_id", "project_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_bill_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchase_bills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    expense_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    line_subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
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

    purchase_bill: Mapped["PurchaseBill"] = relationship("PurchaseBill", back_populates="lines")
    tax_code: Mapped["TaxCode | None"] = relationship("TaxCode")
    expense_account: Mapped["Account | None"] = relationship("Account")
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
    project_cost_code: Mapped["ProjectCostCode | None"] = relationship("ProjectCostCode")
