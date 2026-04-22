from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.administration.models.password_history import PasswordHistory


class PasswordHistoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: PasswordHistory) -> None:
        self._session.add(entry)

    def list_recent_by_user(self, user_id: int, limit: int = 10) -> list[PasswordHistory]:
        stmt = (
            select(PasswordHistory)
            .where(PasswordHistory.user_id == user_id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(limit)
        )
        return list(self._session.scalars(stmt))
