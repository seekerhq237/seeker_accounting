from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.administration.models.role import Role


class RoleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, role_id: int) -> Role | None:
        return self._session.get(Role, role_id)

    def get_by_code(self, code: str) -> Role | None:
        return self._session.scalar(
            select(Role).where(Role.code == code)
        )

    def list_all(self) -> list[Role]:
        return list(self._session.scalars(
            select(Role).order_by(Role.name.asc())
        ))

    def add(self, role: Role) -> Role:
        self._session.add(role)
        return role

    def save(self, role: Role) -> Role:
        self._session.flush()
        return role

    def delete(self, role: Role) -> None:
        self._session.delete(role)
