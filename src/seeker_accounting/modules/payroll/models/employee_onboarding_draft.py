"""Phase 4 Hire-to-Pay business process — draft aggregate.

Persists in-progress employee onboarding runs so the user can leave the
flow and return later. Once the BP completes, this draft is marked
``completed`` and a regular ``Employee`` row is materialised; until
then no employee record exists in the master table.

The state machine and step ordering are owned by the service layer
(:mod:`seeker_accounting.modules.payroll.services.employee_onboarding_service`).
This model only stores the persisted snapshot.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base, TimestampMixin


class EmployeeOnboardingDraft(TimestampMixin, Base):
    """Draft aggregate for the Hire-to-Pay business process."""

    __tablename__ = "employee_onboarding_drafts"
    __table_args__ = (
        Index("ix_employee_onboarding_drafts_company_id", "company_id"),
        Index("ix_employee_onboarding_drafts_status", "status_code"),
        Index(
            "ix_employee_onboarding_drafts_employee_id",
            "produced_employee_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # State machine — see EmployeeOnboardingState for the canonical
    # enum. Stored as a short code for portability.
    status_code: Mapped[str] = mapped_column(String(40), nullable=False)
    current_step: Mapped[str] = mapped_column(String(40), nullable=False)

    # JSON snapshot of step payloads; portable across SQLite / Postgres
    # / Firebird without requiring a backend-specific JSON column type.
    payload_json: Mapped[str] = mapped_column(Text(), nullable=False, default="{}")

    # Audit anchor — who started, who last touched, who closed.
    started_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_modified_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    abandoned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    abandon_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Filled when status_code transitions to ``completed``.
    produced_employee_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
