from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ContractProgressClaimLine(TimestampMixin, Base):
    __tablename__ = "contract_progress_claim_lines"
    __table_args__ = (
        UniqueConstraint("progress_claim_id", "line_number"),
        Index("ix_contract_progress_claim_lines_company_id", "company_id"),
        Index("ix_contract_progress_claim_lines_claim_id", "progress_claim_id"),
        Index("ix_contract_progress_claim_lines_contract_line_id", "contract_line_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    progress_claim_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contract_progress_claims.id", ondelete="RESTRICT"),
        nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_line_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contract_lines.id", ondelete="RESTRICT"),
        nullable=True,
    )
    billing_schedule_item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("contract_billing_schedule_items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    certified_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
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

    company: Mapped["Company"] = relationship("Company")
    progress_claim: Mapped["ContractProgressClaim"] = relationship("ContractProgressClaim", back_populates="lines")
    contract_line: Mapped["ContractLine | None"] = relationship("ContractLine")
    billing_schedule_item: Mapped["ContractBillingScheduleItem | None"] = relationship("ContractBillingScheduleItem")
    project: Mapped["Project | None"] = relationship("Project")
    project_job: Mapped["ProjectJob | None"] = relationship("ProjectJob")
    project_cost_code: Mapped["ProjectCostCode | None"] = relationship("ProjectCostCode")
