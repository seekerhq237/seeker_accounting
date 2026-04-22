from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin


class ProjectBudgetVersion(TimestampMixin, Base):
    __tablename__ = "project_budget_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_number", name="uq_project_budget_versions_project_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_type_code: Mapped[str] = mapped_column(String(20), nullable=False)
    status_code: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    base_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("project_budget_versions.id"), nullable=True
    )
    budget_date: Mapped[date] = mapped_column(Date, nullable=False)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_budget_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Relationships
    company = relationship("Company", foreign_keys=[company_id], lazy="select")
    project = relationship("Project", foreign_keys=[project_id], lazy="select")
    base_version = relationship(
        "ProjectBudgetVersion", remote_side=[id], foreign_keys=[base_version_id], lazy="select"
    )
    approved_by_user = relationship("User", foreign_keys=[approved_by_user_id], lazy="select")
    lines: Mapped[list["ProjectBudgetLine"]] = relationship(
        "ProjectBudgetLine", back_populates="version", lazy="select",
        cascade="all, delete-orphan", order_by="ProjectBudgetLine.line_number",
    )
