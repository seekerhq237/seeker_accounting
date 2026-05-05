from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ContractBillingScheduleItem(TimestampMixin, Base):
    __tablename__ = "contract_billing_schedule_items"
    __table_args__ = (
        UniqueConstraint("contract_id", "line_number"),
        Index("ix_contract_billing_schedule_company_id", "company_id"),
        Index("ix_contract_billing_schedule_contract_id", "contract_id"),
        Index("ix_contract_billing_schedule_contract_line_id", "contract_line_id"),
        Index("ix_contract_billing_schedule_project_id", "project_id"),
        Index("ix_contract_billing_schedule_project_job_id", "project_job_id"),
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
    schedule_type_code: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    milestone_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    billing_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
    scheduled_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    retention_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    advance_recovery_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    time_material_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contract_line_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contract_lines.id", ondelete="RESTRICT"),
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
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    contract: Mapped["Contract"] = relationship("Contract")
    contract_line: Mapped["ContractLine | None"] = relationship("ContractLine")
    project: Mapped["Project | None"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
