from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from seeker_accounting.db.base import Base, utcnow


class UserSession(Base):
    """Tracks login/logout session pairs for audit trail integrity.

    A row with ``logout_at IS NULL`` represents either an active session
    or an abnormal termination (crash, power loss, forced kill).
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    login_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow)
    logout_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    logout_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Abnormal shutdown tracking
    abnormal_explanation_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    abnormal_explanation_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    abnormal_reviewed_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    abnormal_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    # Session metadata
    app_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os_info: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # noqa: F821
    reviewed_by_user: Mapped["User | None"] = relationship(  # noqa: F821
        "User", foreign_keys=[abnormal_reviewed_by_user_id]
    )

    __table_args__ = (
        Index("ix_user_sessions_user_company", "user_id", "company_id"),
        Index("ix_user_sessions_logout_at", "logout_at"),
        Index("ix_user_sessions_abnormal_unreviewed", "company_id", "logout_reason", "abnormal_reviewed_at"),
    )
