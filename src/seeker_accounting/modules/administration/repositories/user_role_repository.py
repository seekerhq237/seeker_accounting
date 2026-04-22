from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.administration.models.user import User
from seeker_accounting.modules.administration.models.role import Role
from seeker_accounting.modules.administration.models.user_role import UserRole


class UserRoleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_user_id(self, user_id: int) -> list[UserRole]:
        return list(self._session.scalars(
            select(UserRole).where(UserRole.user_id == user_id)
        ))

    def list_by_role_id(self, role_id: int) -> list[UserRole]:
        return list(self._session.scalars(
            select(UserRole).where(UserRole.role_id == role_id)
        ))

    def add(self, user_role: UserRole) -> UserRole:
        self._session.add(user_role)
        return user_role

    def delete_by_user_id(self, user_id: int) -> None:
        self._session.execute(
            delete(UserRole).where(UserRole.user_id == user_id)
        )

    def delete_single_assignment(self, user_id: int, role_id: int) -> None:
        self._session.execute(
            delete(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
            )
        )

    def count_active_users_with_role_code(self, role_code: str) -> int:
        """Return the number of *active* users that hold a role with the given code."""
        stmt = (
            select(func.count())
            .select_from(UserRole)
            .join(User, UserRole.user_id == User.id)
            .join(Role, UserRole.role_id == Role.id)
            .where(Role.code == role_code, User.is_active == True)  # noqa: E712
        )
        return self._session.scalar(stmt) or 0
