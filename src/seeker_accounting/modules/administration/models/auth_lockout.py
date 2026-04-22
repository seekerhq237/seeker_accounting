from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from seeker_accounting.db.base import Base, utcnow


class AuthenticationLockout(Base):
    __tablename__ = "authentication_lockouts"

    scope_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False, default=utcnow, onupdate=utcnow)
