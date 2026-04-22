from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from seeker_accounting.modules.administration.models.auth_lockout import AuthenticationLockout


class AuthLockoutRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_scope_key(self, scope_key: str) -> AuthenticationLockout | None:
        return self._session.get(AuthenticationLockout, scope_key)

    def save(self, record: AuthenticationLockout) -> None:
        self._session.add(record)

    def delete_by_scope_key(self, scope_key: str) -> None:
        self._session.execute(
            delete(AuthenticationLockout).where(AuthenticationLockout.scope_key == scope_key)
        )
