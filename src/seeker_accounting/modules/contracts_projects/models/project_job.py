from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ProjectJob(TimestampMixin, Base):
    """A work package / job within a project. Supports hierarchy via parent_job_id."""

    __tablename__ = "project_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "job_code"),
        Index("ix_project_jobs_project_id", "project_id"),
        Index("ix_project_jobs_parent_job_id", "parent_job_id"),
        Index("ix_project_jobs_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_code: Mapped[str] = mapped_column(String(40), nullable=False)
    job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("project_jobs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    start_date: Mapped[datetime | None] = mapped_column(Date(), nullable=True)
    planned_end_date: Mapped[datetime | None] = mapped_column(Date(), nullable=True)
    actual_end_date: Mapped[datetime | None] = mapped_column(Date(), nullable=True)
    allow_direct_cost_posting: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    company: Mapped["Company"] = relationship("Company")
    project: Mapped["Project"] = relationship("Project")
    parent_job: Mapped["ProjectJob | None"] = relationship("ProjectJob", remote_side=[id])
