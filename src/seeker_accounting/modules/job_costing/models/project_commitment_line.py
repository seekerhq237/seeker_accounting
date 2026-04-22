from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ProjectCommitmentLine(TimestampMixin, Base):
    __tablename__ = "project_commitment_lines"
    __table_args__ = (
        UniqueConstraint(
            "project_commitment_id", "line_number",
            name="uq_project_commitment_lines_commitment_line",
        ),
        Index("ix_project_commitment_lines_commitment_job", "project_commitment_id", "project_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_commitment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_commitments.id", ondelete="CASCADE"), nullable=False,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    project_job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("project_jobs.id", ondelete="RESTRICT"), nullable=True,
    )
    project_cost_code_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_cost_codes.id", ondelete="RESTRICT"), nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    line_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    commitment = relationship("ProjectCommitment", back_populates="lines", lazy="select")
    project_job = relationship("ProjectJob", foreign_keys=[project_job_id], lazy="select")
    project_cost_code = relationship("ProjectCostCode", foreign_keys=[project_cost_code_id], lazy="select")
