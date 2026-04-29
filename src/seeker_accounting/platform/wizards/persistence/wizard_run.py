"""ORM model for ``wizard_runs`` table.

Captures a single run of any wizard so that long, multi-step flows
(payroll close, year-end close, company setup) can be paused and resumed.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from seeker_accounting.modules.administration.models.user import User
    from seeker_accounting.modules.companies.models.company import Company


class WizardRun(TimestampMixin, Base):
    """A single execution of a wizard, possibly spanning multiple sessions."""

    __tablename__ = "wizard_runs"
    __table_args__ = (
        Index("ix_wizard_runs_company_id", "company_id"),
        Index("ix_wizard_runs_user_status", "initiated_by_user_id", "status_code"),
        Index("ix_wizard_runs_wizard_code", "wizard_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    #: Wizard archetype (e.g. ``"company_setup"``, ``"month_end_close"``).
    wizard_code: Mapped[str] = mapped_column(String(60), nullable=False)

    #: Company scope. ``NULL`` for wizards that *create* the company in step 1.
    company_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )

    initiated_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step_key: Mapped[str | None] = mapped_column(String(60), nullable=True)

    #: ``draft`` | ``in_progress`` | ``completed`` | ``cancelled`` | ``failed``.
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)

    #: JSON-encoded ``WizardState``. Use :func:`json.loads` / :func:`json.dumps`.
    state_payload: Mapped[str | None] = mapped_column(Text(), nullable=True)

    #: Optional plain-text reason for failure or cancellation.
    failure_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    company: Mapped["Company | None"] = relationship("Company")
    initiated_by_user: Mapped["User"] = relationship(
        "User", foreign_keys=[initiated_by_user_id]
    )
