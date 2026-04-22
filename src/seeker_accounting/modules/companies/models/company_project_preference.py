from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

from seeker_accounting.db.base import Base, utcnow


class CompanyProjectPreference(Base):
    __tablename__ = "company_project_preferences"

    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    allow_projects_without_contract: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default=expression.true(),
    )
    default_budget_control_mode_code: Mapped[str] = mapped_column(String(20), nullable=False)
    default_commitment_control_mode_code: Mapped[str] = mapped_column(String(20), nullable=False)
    budget_warning_percent_threshold: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    require_job_on_cost_posting: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    require_cost_code_on_cost_posting: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    company: Mapped["Company"] = relationship("Company")
    updated_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[updated_by_user_id])