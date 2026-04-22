from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.administration.models.permission import Permission


class PermissionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_code(self, code: str) -> Permission | None:
        return self._session.scalar(
            select(Permission).where(Permission.code == code)
        )

    def list_all(self) -> list[Permission]:
        return list(self._session.scalars(
            select(Permission).order_by(Permission.module_code.asc(), Permission.code.asc())
        ))

    def list_by_role_id(self, role_id: int) -> list[Permission]:
        from seeker_accounting.modules.administration.models.role_permission import RolePermission

        statement = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
            .order_by(Permission.code.asc())
        )
        return list(self._session.scalars(statement))

    def list_by_user_id(self, user_id: int) -> list[Permission]:
        from seeker_accounting.modules.administration.models.role_permission import RolePermission
        from seeker_accounting.modules.administration.models.user_role import UserRole

        statement = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
            .order_by(Permission.code.asc())
        )
        return list(self._session.scalars(statement))

    def add(self, permission: Permission) -> Permission:
        self._session.add(permission)
        return permission
