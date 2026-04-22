"""Audit event model — immutable log of business-sensitive actions.

Each row records one discrete auditable event with its actor, target entity,
and a JSON-serialisable payload of contextual data.  Rows are append-only;
the table has no UPDATE or DELETE workflows.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base, utcnow


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    company_id: Mapped[int] = mapped_column(
        Integer(),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    detail_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer(),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actor_display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, default=utcnow
    )
