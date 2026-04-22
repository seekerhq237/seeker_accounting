from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.db.base import utcnow
from seeker_accounting.modules.administration.models.user_session import UserSession


class UserSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user_session: UserSession) -> UserSession:
        self._session.add(user_session)
        return user_session

    def get_by_id(self, session_id: int) -> UserSession | None:
        return self._session.get(UserSession, session_id)

    def find_open_sessions_for_user(self, user_id: int) -> list[UserSession]:
        """Return sessions with no ``logout_at`` for the given user."""
        stmt = (
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.logout_at.is_(None))
            .order_by(UserSession.login_at.desc())
        )
        return list(self._session.scalars(stmt))

    def find_unreviewed_abnormal_sessions(self, company_id: int) -> list[UserSession]:
        """Return abnormal sessions for the company that an admin has not yet reviewed."""
        stmt = (
            select(UserSession)
            .where(
                UserSession.company_id == company_id,
                UserSession.logout_reason == "abnormal",
                UserSession.abnormal_reviewed_at.is_(None),
            )
            .order_by(UserSession.login_at.desc())
        )
        return list(self._session.scalars(stmt))

    def close_session(self, session_id: int, logout_reason: str) -> None:
        us = self.get_by_id(session_id)
        if us is None:
            return
        us.logout_at = utcnow()
        us.logout_reason = logout_reason

    def resolve_abnormal(
        self,
        session_id: int,
        explanation_code: str,
        explanation_note: str | None,
    ) -> None:
        us = self.get_by_id(session_id)
        if us is None:
            return
        now = utcnow()
        us.logout_at = us.logout_at or now
        us.logout_reason = "abnormal"
        us.abnormal_explanation_code = explanation_code
        us.abnormal_explanation_note = explanation_note

    def mark_reviewed(self, session_id: int, reviewed_by_user_id: int) -> None:
        us = self.get_by_id(session_id)
        if us is None:
            return
        us.abnormal_reviewed_by_user_id = reviewed_by_user_id
        us.abnormal_reviewed_at = utcnow()
