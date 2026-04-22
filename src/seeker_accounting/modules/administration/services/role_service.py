"""RoleService — manages role CRUD and permission assignment.

This service owns all role lifecycle operations and the assignment of
permissions to roles.  It does not manage user-to-role assignment (that
remains in ``UserAuthService``).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.dto.role_commands import (
    AssignRolePermissionsCommand,
    CreateRoleCommand,
    UpdateRoleCommand,
)
from seeker_accounting.modules.administration.dto.user_dto import (
    PermissionDTO,
    RoleDTO,
    RoleWithPermissionsDTO,
)
from seeker_accounting.modules.administration.models.role import Role
from seeker_accounting.modules.administration.models.permission import Permission
from seeker_accounting.modules.administration.repositories.permission_repository import PermissionRepository
from seeker_accounting.modules.administration.repositories.role_permission_repository import (
    RolePermissionRepository,
)
from seeker_accounting.modules.administration.repositories.role_repository import RoleRepository
from seeker_accounting.modules.administration.repositories.user_role_repository import UserRoleRepository
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

RoleRepositoryFactory = Callable[[Session], RoleRepository]
PermissionRepositoryFactory = Callable[[Session], PermissionRepository]
RolePermissionRepositoryFactory = Callable[[Session], RolePermissionRepository]
UserRoleRepositoryFactory = Callable[[Session], UserRoleRepository]

_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,98}$")


class RoleService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        role_repository_factory: RoleRepositoryFactory,
        permission_repository_factory: PermissionRepositoryFactory,
        role_permission_repository_factory: RolePermissionRepositoryFactory,
        user_role_repository_factory: UserRoleRepositoryFactory,
        permission_service: PermissionService,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._role_repo_factory = role_repository_factory
        self._permission_repo_factory = permission_repository_factory
        self._role_perm_repo_factory = role_permission_repository_factory
        self._user_role_repo_factory = user_role_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ── Queries ──────────────────────────────────────────────────────

    def list_roles(self) -> list[RoleDTO]:
        self._require("administration.roles.view")
        with self._uow_factory() as uow:
            repo = self._role_repo_factory(uow.session)
            return [self._to_role_dto(r) for r in repo.list_all()]

    def get_role(self, role_id: int) -> RoleWithPermissionsDTO:
        self._require("administration.roles.view")
        with self._uow_factory() as uow:
            role_repo = self._role_repo_factory(uow.session)
            role = role_repo.get_by_id(role_id)
            if role is None:
                raise NotFoundError(f"Role with id {role_id} was not found.")
            perm_repo = self._permission_repo_factory(uow.session)
            perms = perm_repo.list_by_role_id(role_id)
            return RoleWithPermissionsDTO(
                role=self._to_role_dto(role),
                permissions=tuple(self._to_permission_dto(p) for p in perms),
            )

    def list_all_permissions(self) -> list[PermissionDTO]:
        self._require("administration.permissions.view")
        with self._uow_factory() as uow:
            repo = self._permission_repo_factory(uow.session)
            return [self._to_permission_dto(p) for p in repo.list_all()]

    # ── Commands ─────────────────────────────────────────────────────

    def create_role(self, command: CreateRoleCommand) -> RoleDTO:
        self._require("administration.roles.create")

        code = command.code.strip().lower()
        name = command.name.strip()

        if not code:
            raise ValidationError("Role code is required.")
        if not _CODE_PATTERN.match(code):
            raise ValidationError(
                "Role code must start with a letter and contain only lowercase letters, digits, and underscores (2–99 characters)."
            )
        if not name:
            raise ValidationError("Role name is required.")

        with self._uow_factory() as uow:
            repo = self._role_repo_factory(uow.session)
            if repo.get_by_code(code) is not None:
                raise ConflictError(f"A role with code '{code}' already exists.")

            role = Role(
                code=code,
                name=name,
                description=command.description.strip() if command.description else None,
                is_system=False,
            )
            repo.add(role)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError(f"Role '{code}' could not be created due to a conflict.") from exc

            from seeker_accounting.modules.audit.event_type_catalog import ROLE_CREATED
            self._record_audit(0, ROLE_CREATED, "Role", role.id, f"Created role '{code}'")
            return self._to_role_dto(role)

    def update_role(self, command: UpdateRoleCommand) -> RoleDTO:
        self._require("administration.roles.edit")

        name = command.name.strip()
        if not name:
            raise ValidationError("Role name is required.")

        with self._uow_factory() as uow:
            repo = self._role_repo_factory(uow.session)
            role = repo.get_by_id(command.role_id)
            if role is None:
                raise NotFoundError(f"Role with id {command.role_id} was not found.")

            role.name = name
            role.description = command.description.strip() if command.description else None
            repo.save(role)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ROLE_UPDATED
            self._record_audit(0, ROLE_UPDATED, "Role", role.id, f"Updated role id={command.role_id}")
            return self._to_role_dto(role)

    def delete_role(self, role_id: int) -> None:
        self._require("administration.roles.delete")

        with self._uow_factory() as uow:
            role_repo = self._role_repo_factory(uow.session)
            role = role_repo.get_by_id(role_id)
            if role is None:
                raise NotFoundError(f"Role with id {role_id} was not found.")
            if role.is_system:
                raise ValidationError("System roles cannot be deleted.")

            user_role_repo = self._user_role_repo_factory(uow.session)
            assignments = user_role_repo.list_by_role_id(role_id)
            if assignments:
                raise ValidationError(
                    "This role is assigned to one or more users and cannot be deleted. "
                    "Remove the role from all users first."
                )

            rp_repo = self._role_perm_repo_factory(uow.session)
            rp_repo.replace_for_role(role_id, [])
            role_repo.delete(role)
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ROLE_DELETED
            self._record_audit(0, ROLE_DELETED, "Role", role_id, f"Deleted role id={role_id}")

    def assign_permissions(self, command: AssignRolePermissionsCommand) -> None:
        self._require("administration.role_permissions.assign")

        with self._uow_factory() as uow:
            role_repo = self._role_repo_factory(uow.session)
            role = role_repo.get_by_id(command.role_id)
            if role is None:
                raise NotFoundError(f"Role with id {command.role_id} was not found.")

            perm_repo = self._permission_repo_factory(uow.session)
            all_perms = {p.id for p in perm_repo.list_all()}
            invalid = set(command.permission_ids) - all_perms
            if invalid:
                raise ValidationError(f"Invalid permission IDs: {sorted(invalid)}")

            rp_repo = self._role_perm_repo_factory(uow.session)
            rp_repo.replace_for_role(command.role_id, list(command.permission_ids))
            uow.commit()
            from seeker_accounting.modules.audit.event_type_catalog import ROLE_PERMISSIONS_ASSIGNED
            self._record_audit(0, ROLE_PERMISSIONS_ASSIGNED, "Role", command.role_id, f"Assigned permissions to role id={command.role_id}")

    # ── Internal helpers ─────────────────────────────────────────────

    def _require(self, permission_code: str) -> None:
        if self._permission_service.has_authenticated_actor():
            self._permission_service.require_permission(permission_code)

    @staticmethod
    def _to_role_dto(role: Role) -> RoleDTO:
        return RoleDTO(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
        )

    @staticmethod
    def _to_permission_dto(perm: Permission) -> PermissionDTO:
        return PermissionDTO(
            id=perm.id,
            code=perm.code,
            name=perm.name,
            module_code=perm.module_code,
            description=perm.description,
        )

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
    ) -> None:
        if self._audit_service is None:
            return
        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
        from seeker_accounting.modules.audit.event_type_catalog import MODULE_AUTH
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_AUTH,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                ),
            )
        except Exception:
            pass  # Audit must not break business operations
