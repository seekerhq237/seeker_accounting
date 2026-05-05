from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ContractLine(TimestampMixin, Base):
    __tablename__ = "contract_lines"
    __table_args__ = (
        UniqueConstraint("contract_id", "line_number"),
        Index("ix_contract_lines_company_id", "company_id"),
        Index("ix_contract_lines_contract_id", "contract_id"),
        Index("ix_contract_lines_change_order_id", "change_order_id"),
        Index("ix_contract_lines_project_id", "project_id"),
        Index("ix_contract_lines_project_job_id", "project_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contract_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_code_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tax_codes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tax_treatment_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    billing_basis_code: Mapped[str] = mapped_column(String(30), nullable=False)
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
    change_order_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contract_change_orders.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    contract: Mapped["Contract"] = relationship("Contract")
    tax_code: Mapped["TaxCode | None"] = relationship("TaxCode")
    project: Mapped["Project | None"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
    change_order: Mapped["ContractChangeOrder | None"] = relationship("ContractChangeOrder")
