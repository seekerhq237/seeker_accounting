from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class SalesOrderLine(TimestampMixin, Base):
    __tablename__ = "sales_order_lines"
    __table_args__ = (
        UniqueConstraint("sales_order_id", "line_number"),
        Index("ix_sales_order_lines_project_id", "project_id"),
        Index("ix_sales_order_lines_project_job_id", "project_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sales_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    revenue_account_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
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
    # P2 / Slice 3.1 – inventory item linkage
    item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=True
    )
    uom_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("units_of_measure.id", ondelete="RESTRICT"), nullable=True
    )
    uom_ratio_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    base_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_cost_at_issue: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    cogs_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    sales_order: Mapped["SalesOrder"] = relationship("SalesOrder", back_populates="lines")
    tax_code: Mapped["TaxCode | None"] = relationship("TaxCode")
    revenue_account: Mapped["Account | None"] = relationship("Account")
    contract: Mapped["Contract | None"] = relationship("Contract")
    project: Mapped["Project | None"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
    project_cost_code: Mapped["ProjectCostCode | None"] = relationship("ProjectCostCode")
    tax_details: Mapped[list["SalesOrderLineTax"]] = relationship(
        "SalesOrderLineTax",
        back_populates="sales_order_line",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
