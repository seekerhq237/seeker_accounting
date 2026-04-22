from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.administration.models.role_permission import RolePermission


class RolePermissionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_role_id(self, role_id: int) -> list[RolePermission]:
        return list(self._session.scalars(
            select(RolePermission).where(RolePermission.role_id == role_id)
        ))

    def replace_for_role(self, role_id: int, permission_ids: list[int]) -> None:
        """Atomically replace all permission assignments for a role."""
        self._session.execute(
            delete(RolePermission).where(RolePermission.role_id == role_id)
        )
        for pid in permission_ids:
            self._session.add(RolePermission(role_id=role_id, permission_id=pid))
        self._session.flush()
