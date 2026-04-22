from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ProjectBudgetLine(TimestampMixin, Base):
    __tablename__ = "project_budget_lines"
    __table_args__ = (
        UniqueConstraint(
            "project_budget_version_id", "line_number",
            name="uq_project_budget_lines_version_line",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_budget_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_budget_versions.id"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    project_job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("project_jobs.id"), nullable=True
    )
    project_cost_code_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_cost_codes.id"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    line_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    version = relationship("ProjectBudgetVersion", back_populates="lines", lazy="select")
    project_job = relationship("ProjectJob", foreign_keys=[project_job_id], lazy="select")
    project_cost_code = relationship("ProjectCostCode", foreign_keys=[project_cost_code_id], lazy="select")
