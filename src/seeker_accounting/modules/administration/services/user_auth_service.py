"""UserAuthService — handles password hashing, verification, user creation, and login.

This service owns all password-related operations and login credential verification.
It bridges the administration repositories with a secure bcrypt-based password system.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

import json

import bcrypt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.dto.user_commands import ChangePasswordCommand, CreateUserCommand, UpdateUserCommand
from seeker_accounting.modules.administration.dto.user_dto import (
    AuthenticatedUserDTO,
    LoginResultDTO,
    RoleDTO,
    UserDTO,
    UserWithRolesDTO,
)
from seeker_accounting.modules.administration.models.auth_lockout import AuthenticationLockout
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.event_type_catalog import (
    MODULE_AUTH,
    USER_COMPANY_ACCESS_GRANTED,
    USER_CREATED,
    USER_DEACTIVATED,
    USER_ACTIVATED,
    USER_DELETED,
    USER_LOGIN_FAILED,
    USER_LOGIN_SUCCESS,
    USER_PASSWORD_CHANGED,
    USER_ROLE_ASSIGNED,
    USER_ROLE_REVOKED,
    USER_UPDATED,
)
from seeker_accounting.modules.administration.models.user import User
from seeker_accounting.modules.administration.models.role import Role
from seeker_accounting.modules.administration.models.user_company_access import UserCompanyAccess
from seeker_accounting.modules.administration.models.user_role import UserRole
from seeker_accounting.modules.administration.repositories.permission_repository import PermissionRepository
from seeker_accounting.modules.administration.repositories.role_repository import RoleRepository
from seeker_accounting.modules.administration.repositories.auth_lockout_repository import AuthLockoutRepository
from seeker_accounting.modules.administration.repositories.user_company_access_repository import (
    UserCompanyAccessRepository,
)
from seeker_accounting.modules.administration.repositories.user_repository import UserRepository
from seeker_accounting.modules.administration.repositories.user_role_repository import UserRoleRepository
from seeker_accounting.modules.administration.repositories.password_history_repository import PasswordHistoryRepository
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.companies.repositories.company_preference_repository import CompanyPreferenceRepository
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

if TYPE_CHECKING:
    from seeker_accounting.modules.audit.services.audit_service import AuditService

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CompanyPreferenceRepositoryFactory = Callable[[Session], CompanyPreferenceRepository]

UserRepositoryFactory = Callable[[Session], UserRepository]
RoleRepositoryFactory = Callable[[Session], RoleRepository]
UserRoleRepositoryFactory = Callable[[Session], UserRoleRepository]
UserCompanyAccessRepositoryFactory = Callable[[Session], UserCompanyAccessRepository]
PermissionRepositoryFactory = Callable[[Session], PermissionRepository]
PasswordHistoryRepositoryFactory = Callable[[Session], PasswordHistoryRepository]
AuthLockoutRepositoryFactory = Callable[[Session], AuthLockoutRepository]

_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_DURATION = timedelta(minutes=15)
_PASSWORD_HISTORY_DEPTH = 10
_ADMIN_ALIAS = "admin"
_log = logging.getLogger(__name__)


class UserAuthService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        user_repository_factory: UserRepositoryFactory,
        role_repository_factory: RoleRepositoryFactory,
        user_role_repository_factory: UserRoleRepositoryFactory,
        user_company_access_repository_factory: UserCompanyAccessRepositoryFactory,
        permission_repository_factory: PermissionRepositoryFactory,
        permission_service: PermissionService,
        company_repository_factory: CompanyRepositoryFactory | None = None,
        company_preference_repository_factory: CompanyPreferenceRepositoryFactory | None = None,
        password_history_repository_factory: PasswordHistoryRepositoryFactory | None = None,
        auth_lockout_repository_factory: AuthLockoutRepositoryFactory | None = None,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._user_repository_factory = user_repository_factory
        self._role_repository_factory = role_repository_factory
        self._user_role_repository_factory = user_role_repository_factory
        self._user_company_access_repository_factory = user_company_access_repository_factory
        self._permission_repository_factory = permission_repository_factory
        self._permission_service = permission_service
        self._company_repository_factory = company_repository_factory
        self._company_preference_repository_factory = company_preference_repository_factory
        self._password_history_repository_factory = password_history_repository_factory
        self._auth_lockout_repository_factory = auth_lockout_repository_factory
        self._audit_service = audit_service
        self._failed_attempts: dict[str, tuple[int, datetime]] = {}

    @staticmethod
    def hash_password(plain_password: str) -> str:
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    def create_user(self, command: CreateUserCommand) -> UserDTO:
        self._require_permission_if_authenticated("administration.users.create")
        username = command.username.strip()
        display_name = command.display_name.strip()
        if not username:
            raise ValidationError("Username is required.")
        if not display_name:
            raise ValidationError("Display name is required.")
        if not command.password:
            raise ValidationError("Password is required.")
        if len(command.password) < 8:
            raise ValidationError("Password must be at least 8 characters.")

        password_hash = self.hash_password(command.password)

        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            existing = user_repo.get_by_username(username)
            if existing is not None:
                raise ConflictError(f"A user with username '{username}' already exists.")

            user = User(
                username=username,
                display_name=display_name,
                email=command.email.strip() if command.email else None,
                password_hash=password_hash,
                must_change_password=command.must_change_password,
                password_changed_at=datetime.utcnow(),
            )
            user_repo.add(user)

            try:
                uow.commit()
            except IntegrityError as exc:
                raise ConflictError(f"User '{username}' could not be created due to a conflict.") from exc

            self._record_audit(
                company_id=0,
                event_type_code=USER_CREATED,
                entity_type="User",
                entity_id=user.id,
                description=f"User '{username}' created.",
                detail_json=json.dumps({"username": username, "display_name": display_name}),
            )
            return self._to_user_dto(user)

    def authenticate(self, username: str, password: str) -> AuthenticatedUserDTO:
        entered_username = username.strip()
        if not entered_username:
            raise ValidationError("Username is required.")

        rate_key = entered_username.lower()
        self._check_rate_limit(rate_key)

        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            user = user_repo.get_by_username(entered_username)

            if user is None or not user.is_active:
                self._record_failed_attempt(rate_key)
                self._record_audit(
                    company_id=0,
                    event_type_code=USER_LOGIN_FAILED,
                    entity_type="User",
                    entity_id=None,
                    description=f"Failed login attempt for '{entered_username}'.",
                )
                raise ValidationError("Invalid username or password.")

            if not self.verify_password(password, user.password_hash):
                self._record_failed_attempt(rate_key)
                self._record_audit(
                    company_id=0,
                    event_type_code=USER_LOGIN_FAILED,
                    entity_type="User",
                    entity_id=user.id,
                    description=f"Failed login (bad password) for '{user.username}'.",
                )
                raise ValidationError("Invalid username or password.")

            self._clear_failed_attempts(rate_key)

            return AuthenticatedUserDTO(
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                must_change_password=user.must_change_password,
            )

    def complete_login(self, user_id: int, company_id: int) -> LoginResultDTO:
        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            access_repo = self._user_company_access_repository_factory(uow.session)
            permission_repo = self._permission_repository_factory(uow.session)

            user = user_repo.get_by_id(user_id)
            if user is None or not user.is_active:
                raise ValidationError("Invalid username or password.")

            access = access_repo.get_by_user_and_company(user_id, company_id)
            if access is None:
                self._record_audit(
                    company_id=company_id,
                    event_type_code=USER_LOGIN_FAILED,
                    entity_type="User",
                    entity_id=user.id,
                    description=f"Login denied — no company access for '{user.username}'.",
                )
                raise ValidationError("You do not have access to that organisation.")

            permissions = permission_repo.list_by_user_id(user.id)
            permission_codes = tuple(permission.code for permission in permissions)

            password_expired = False
            if self._company_preference_repository_factory is not None:
                pref_repo = self._company_preference_repository_factory(uow.session)
                pref = pref_repo.get_by_company_id(company_id)
                expiry_days = pref.password_expiry_days if pref is not None else 30
                if expiry_days > 0 and user.password_changed_at is not None:
                    age = datetime.utcnow() - user.password_changed_at
                    if age.days >= expiry_days:
                        password_expired = True

            user.last_login_at = datetime.utcnow()
            user_repo.save(user)
            uow.commit()

            self._record_audit(
                company_id=company_id,
                event_type_code=USER_LOGIN_SUCCESS,
                entity_type="User",
                entity_id=user.id,
                description=f"User '{user.username}' logged in.",
            )
            return LoginResultDTO(
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                must_change_password=user.must_change_password,
                password_expired=password_expired,
                permission_codes=permission_codes,
            )

    def authenticate_for_company(
        self, company_id: int, username: str, password: str
    ) -> LoginResultDTO:
        """Company-first login with alias resolution.

        If *username* is ``admin`` (case-insensitive), resolve it to the
        company's actual admin account (``admin_{name}_{id}``).  Otherwise
        verify the user has access to the selected company.
        """
        entered_username = username.strip()
        if not entered_username:
            raise ValidationError("Username is required.")

        rate_key = f"{entered_username.lower()}@company:{company_id}"
        self._check_rate_limit(rate_key)

        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            access_repo = self._user_company_access_repository_factory(uow.session)

            resolved_user = self._resolve_user_for_company(
                entered_username, company_id, user_repo, access_repo
            )

            if resolved_user is None or not resolved_user.is_active:
                self._record_failed_attempt(rate_key)
                self._record_audit(
                    company_id=company_id,
                    event_type_code=USER_LOGIN_FAILED,
                    entity_type="User",
                    entity_id=None,
                    description=f"Failed login attempt for '{entered_username}'.",
                )
                raise ValidationError("Invalid username or password.")

            if not self.verify_password(password, resolved_user.password_hash):
                self._record_failed_attempt(rate_key)
                self._record_audit(
                    company_id=company_id,
                    event_type_code=USER_LOGIN_FAILED,
                    entity_type="User",
                    entity_id=resolved_user.id,
                    description=f"Failed login (bad password) for '{resolved_user.username}'.",
                )
                raise ValidationError("Invalid username or password.")

            # Verify company access
            access = access_repo.get_by_user_and_company(resolved_user.id, company_id)
            if access is None:
                self._record_failed_attempt(rate_key)
                self._record_audit(
                    company_id=company_id,
                    event_type_code=USER_LOGIN_FAILED,
                    entity_type="User",
                    entity_id=resolved_user.id,
                    description=f"Login denied — no company access for '{resolved_user.username}'.",
                )
                raise ValidationError("Invalid username or password.")

            permission_repo = self._permission_repository_factory(uow.session)
            permissions = permission_repo.list_by_user_id(resolved_user.id)
            permission_codes = tuple(p.code for p in permissions)

            self._clear_failed_attempts(rate_key)

            resolved_user.last_login_at = datetime.utcnow()
            user_repo.save(resolved_user)
            uow.commit()

            # Check password expiry
            password_expired = False
            if self._company_preference_repository_factory is not None:
                pref_repo = self._company_preference_repository_factory(uow.session)
                pref = pref_repo.get_by_company_id(company_id)
                expiry_days = pref.password_expiry_days if pref is not None else 30
                if expiry_days > 0 and resolved_user.password_changed_at is not None:
                    age = datetime.utcnow() - resolved_user.password_changed_at
                    if age.days >= expiry_days:
                        password_expired = True

            self._record_audit(
                company_id=company_id,
                event_type_code=USER_LOGIN_SUCCESS,
                entity_type="User",
                entity_id=resolved_user.id,
                description=f"User '{resolved_user.username}' logged in.",
            )
            return LoginResultDTO(
                user_id=resolved_user.id,
                username=resolved_user.username,
                display_name=resolved_user.display_name,
                must_change_password=resolved_user.must_change_password,
                password_expired=password_expired,
                permission_codes=permission_codes,
            )

    @staticmethod
    def _resolve_user_for_company(
        entered_username: str,
        company_id: int,
        user_repo: UserRepository,
        access_repo: UserCompanyAccessRepository,
    ) -> User | None:
        """Resolve the entered username within the company scope.

        If the user typed ``admin``, look for the company's conventional admin
        account (``admin_*_{company_id}``).  Otherwise do a direct lookup and
        verify company access.
        """
        if entered_username.lower() == _ADMIN_ALIAS:
            company_users = user_repo.list_by_company_id(company_id)
            suffix = f"_{company_id}"
            # Prefer the conventional admin_{name}_{id} pattern
            for u in company_users:
                if u.username.startswith("admin_") and u.username.endswith(suffix):
                    return u
            # Fall back to an exact "admin" username with company access
            for u in company_users:
                if u.username == _ADMIN_ALIAS:
                    return u
            return None

        # Direct username lookup — verify the user has access to this company
        user = user_repo.get_by_username(entered_username)
        if user is None:
            return None
        access = access_repo.get_by_user_and_company(user.id, company_id)
        if access is None:
            return None
        return user

    def change_password(self, command: ChangePasswordCommand) -> None:
        current_user_id = self._permission_service.current_user_id
        if current_user_id is not None and current_user_id != command.user_id:
            self._permission_service.require_permission("administration.users.edit")
        if not command.new_password:
            raise ValidationError("New password is required.")
        if len(command.new_password) < 8:
            raise ValidationError("Password must be at least 8 characters.")

        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            user = user_repo.get_by_id(command.user_id)
            if user is None:
                raise NotFoundError(f"User with id {command.user_id} was not found.")

            # Verify current password if provided (voluntary self-service change)
            if command.current_password is not None:
                if not self.verify_password(command.current_password, user.password_hash):
                    raise ValidationError("Current password is incorrect.")

            # Check password history (reuse prevention)
            if self._password_history_repository_factory is not None:
                history_repo = self._password_history_repository_factory(uow.session)
                recent_hashes = history_repo.list_recent_by_user(user.id, limit=_PASSWORD_HISTORY_DEPTH)
                for entry in recent_hashes:
                    if bcrypt.checkpw(command.new_password.encode("utf-8"), entry.password_hash.encode("utf-8")):
                        raise ValidationError(
                            f"New password cannot be the same as any of your last {_PASSWORD_HISTORY_DEPTH} passwords."
                        )
                # Also check against the current password
                if bcrypt.checkpw(command.new_password.encode("utf-8"), user.password_hash.encode("utf-8")):
                    raise ValidationError(
                        f"New password cannot be the same as any of your last {_PASSWORD_HISTORY_DEPTH} passwords."
                    )

                # Store old hash in history before overwriting
                from seeker_accounting.modules.administration.models.password_history import PasswordHistory
                history_repo.add(PasswordHistory(
                    user_id=user.id,
                    password_hash=user.password_hash,
                ))

            user.password_hash = self.hash_password(command.new_password)
            user.must_change_password = False
            user.password_changed_at = datetime.utcnow()
            user_repo.save(user)
            uow.commit()

            self._record_audit(
                company_id=0,
                event_type_code=USER_PASSWORD_CHANGED,
                entity_type="User",
                entity_id=user.id,
                description=f"Password changed for user '{user.username}'.",
            )

    def grant_company_access(
        self,
        user_id: int,
        company_id: int,
        is_default: bool = False,
        granted_by_user_id: int | None = None,
    ) -> None:
        self._require_permission_if_authenticated("administration.company_access.assign")
        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            access_repo = self._user_company_access_repository_factory(uow.session)

            user = user_repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User with id {user_id} was not found.")

            existing = access_repo.get_by_user_and_company(user_id, company_id)
            if existing is not None:
                return  # already granted

            access = UserCompanyAccess(
                user_id=user_id,
                company_id=company_id,
                is_default_company=is_default,
                granted_by_user_id=granted_by_user_id,
            )
            access_repo.add(access)
            uow.commit()

            self._record_audit(
                company_id=company_id,
                event_type_code=USER_COMPANY_ACCESS_GRANTED,
                entity_type="UserCompanyAccess",
                entity_id=user_id,
                description=f"Company access granted to user '{user.username}'.",
            )

    def assign_role(self, user_id: int, role_id: int) -> None:
        self._require_permission_if_authenticated("administration.user_roles.assign")
        with self._unit_of_work_factory() as uow:
            user_role_repo = self._user_role_repository_factory(uow.session)

            existing_roles = user_role_repo.list_by_user_id(user_id)
            if any(ur.role_id == role_id for ur in existing_roles):
                return  # already assigned

            user_role = UserRole(user_id=user_id, role_id=role_id)
            user_role_repo.add(user_role)
            uow.commit()

            self._record_audit(
                company_id=0,
                event_type_code=USER_ROLE_ASSIGNED,
                entity_type="UserRole",
                entity_id=user_id,
                description=f"Role id={role_id} assigned to user id={user_id}.",
            )

    def assign_role_by_code(self, user_id: int, role_code: str) -> None:
        self._require_permission_if_authenticated("administration.user_roles.assign")
        normalized_role_code = role_code.strip()
        if not normalized_role_code:
            raise ValidationError("Role code is required.")

        with self._unit_of_work_factory() as uow:
            role_repo = self._role_repository_factory(uow.session)
            user_role_repo = self._user_role_repository_factory(uow.session)

            role = role_repo.get_by_code(normalized_role_code)
            if role is None:
                raise NotFoundError(f"Role '{normalized_role_code}' was not found.")

            existing_roles = user_role_repo.list_by_user_id(user_id)
            if any(user_role.role_id == role.id for user_role in existing_roles):
                return

            user_role_repo.add(UserRole(user_id=user_id, role_id=role.id))
            uow.commit()

    def get_user(self, user_id: int) -> UserDTO:
        self._require_permission_if_authenticated("administration.users.view")
        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            user = user_repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User with id {user_id} was not found.")
            return self._to_user_dto(user)

    def get_user_permission_codes(self, user_id: int) -> tuple[str, ...]:
        self._require_permission_if_authenticated("administration.users.view")
        with self._unit_of_work_factory() as uow:
            permission_repo = self._permission_repository_factory(uow.session)
            permissions = permission_repo.list_by_user_id(user_id)
            return tuple(p.code for p in permissions)

    def delete_user(self, user_id: int) -> None:
        self._require_permission_if_authenticated("administration.users.delete")
        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            user_role_repo = self._user_role_repository_factory(uow.session)
            access_repo = self._user_company_access_repository_factory(uow.session)

            user = user_repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User with id {user_id} was not found.")

            user_role_repo.delete_by_user_id(user_id)
            for access_entry in access_repo.list_by_user_id(user_id):
                access_repo.delete_by_user_and_company(user_id, access_entry.company_id)

            username = user.username
            uid = user.id
            user_repo.delete(user)
            uow.commit()

            self._record_audit(
                company_id=0,
                event_type_code=USER_DELETED,
                entity_type="User",
                entity_id=uid,
                description=f"User '{username}' deleted.",
            )

    @staticmethod
    def _to_user_dto(user: User) -> UserDTO:
        return UserDTO(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            avatar_storage_path=user.avatar_storage_path,
        )

    @staticmethod
    def _to_role_dto(role: Role) -> RoleDTO:
        return RoleDTO(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
        )

    def list_users_for_company(self, company_id: int) -> list[UserWithRolesDTO]:
        self._require_permission_if_authenticated("administration.users.view")
        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            user_role_repo = self._user_role_repository_factory(uow.session)
            role_repo = self._role_repository_factory(uow.session)

            users = user_repo.list_by_company_id(company_id)
            result = []
            for user in users:
                user_role_records = user_role_repo.list_by_user_id(user.id)
                roles = tuple(
                    self._to_role_dto(role)
                    for ur in user_role_records
                    for role in [role_repo.get_by_id(ur.role_id)]
                    if role is not None
                )
                result.append(UserWithRolesDTO(
                    user=self._to_user_dto(user),
                    roles=roles,
                ))
            return result

    def list_roles(self) -> list[RoleDTO]:
        self._require_permission_if_authenticated("administration.user_roles.assign")
        with self._unit_of_work_factory() as uow:
            role_repo = self._role_repository_factory(uow.session)
            return [self._to_role_dto(r) for r in role_repo.list_all()]

    def get_user_roles(self, user_id: int) -> list[RoleDTO]:
        self._require_permission_if_authenticated("administration.user_roles.assign")
        with self._unit_of_work_factory() as uow:
            user_role_repo = self._user_role_repository_factory(uow.session)
            role_repo = self._role_repository_factory(uow.session)
            result = []
            for ur in user_role_repo.list_by_user_id(user_id):
                role = role_repo.get_by_id(ur.role_id)
                if role is not None:
                    result.append(self._to_role_dto(role))
            return result

    def set_user_active(self, user_id: int, is_active: bool) -> None:
        self._require_permission_if_authenticated("administration.users.deactivate")

        if not is_active:
            current_user_id = self._permission_service.current_user_id
            if current_user_id is not None and current_user_id == user_id:
                raise ValidationError("You cannot deactivate your own account.")

        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            user = user_repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User with id {user_id} was not found.")

            if not is_active:
                user_role_repo = self._user_role_repository_factory(uow.session)
                role_repo = self._role_repository_factory(uow.session)
                admin_role = role_repo.get_by_code("company_admin")
                if admin_role is not None:
                    # Check if this user holds the admin role
                    user_has_admin = any(
                        ur.role_id == admin_role.id
                        for ur in user_role_repo.list_by_user_id(user_id)
                    )
                    if user_has_admin:
                        active_admin_count = user_role_repo.count_active_users_with_role_code("company_admin")
                        if active_admin_count <= 1:
                            raise ValidationError(
                                "Cannot deactivate the only active administrator."
                            )

            user.is_active = is_active
            user_repo.save(user)
            uow.commit()

            evt = USER_ACTIVATED if is_active else USER_DEACTIVATED
            self._record_audit(
                company_id=0,
                event_type_code=evt,
                entity_type="User",
                entity_id=user_id,
                description=f"User '{user.username}' {'activated' if is_active else 'deactivated'}.",
            )

    def revoke_role(self, user_id: int, role_id: int) -> None:
        self._require_permission_if_authenticated("administration.user_roles.assign")

        current_user_id = self._permission_service.current_user_id
        if current_user_id is not None and current_user_id == user_id:
            raise ValidationError("You cannot modify your own role assignments.")

        with self._unit_of_work_factory() as uow:
            user_role_repo = self._user_role_repository_factory(uow.session)
            role_repo = self._role_repository_factory(uow.session)

            role = role_repo.get_by_id(role_id)
            if role is not None and role.code == "company_admin":
                active_admin_count = user_role_repo.count_active_users_with_role_code("company_admin")
                if active_admin_count <= 1:
                    raise ValidationError(
                        "Cannot remove the last administrator role."
                    )

            user_role_repo.delete_single_assignment(user_id, role_id)
            uow.commit()

            self._record_audit(
                company_id=0,
                event_type_code=USER_ROLE_REVOKED,
                entity_type="UserRole",
                entity_id=user_id,
                description=f"Role id={role_id} revoked from user id={user_id}.",
            )

    def update_user(self, command: UpdateUserCommand) -> UserDTO:
        self._require_permission_if_authenticated("administration.users.edit")
        display_name = command.display_name.strip()
        if not display_name:
            raise ValidationError("Display name is required.")

        with self._unit_of_work_factory() as uow:
            user_repo = self._user_repository_factory(uow.session)
            user = user_repo.get_by_id(command.user_id)
            if user is None:
                raise NotFoundError(f"User with id {command.user_id} was not found.")
            user.display_name = display_name
            user.email = command.email.strip() if command.email else None
            user.must_change_password = command.must_change_password
            user_repo.save(user)
            uow.commit()

            self._record_audit(
                company_id=0,
                event_type_code=USER_UPDATED,
                entity_type="User",
                entity_id=user.id,
                description=f"User '{user.username}' updated.",
            )
            return self._to_user_dto(user)

    # ── rate limiting helpers ────────────────────────────────────────

    def _check_rate_limit(self, key: str) -> None:
        """Raise ``ValidationError`` if the account is temporarily locked out."""
        if self._auth_lockout_repository_factory is not None:
            now = datetime.utcnow()
            with self._unit_of_work_factory() as uow:
                repo = self._auth_lockout_repository_factory(uow.session)
                record = repo.get_by_scope_key(key)
                if record is None:
                    return
                if record.locked_until is None:
                    return
                if record.locked_until <= now:
                    repo.delete_by_scope_key(key)
                    uow.commit()
                    return

                remaining = int((record.locked_until - now).total_seconds() // 60) + 1
                _log.warning("Login rate-limited for key '%s' (%d failed attempts)", key, record.failed_count)
                raise ValidationError(
                    f"Too many failed login attempts. Please try again in {remaining} minute{'s' if remaining != 1 else ''}."
                )

        record = self._failed_attempts.get(key)
        if record is None:
            return
        fail_count, last_failure = record
        if fail_count >= _MAX_FAILED_ATTEMPTS:
            elapsed = datetime.utcnow() - last_failure
            if elapsed < _LOCKOUT_DURATION:
                remaining = int((_LOCKOUT_DURATION - elapsed).total_seconds() // 60) + 1
                _log.warning("Login rate-limited for key '%s' (%d failed attempts)", key, fail_count)
                raise ValidationError(
                    f"Too many failed login attempts. Please try again in {remaining} minute{'s' if remaining != 1 else ''}."
                )
            # Lockout expired — reset
            del self._failed_attempts[key]

    def _record_failed_attempt(self, key: str) -> None:
        if self._auth_lockout_repository_factory is not None:
            now = datetime.utcnow()
            with self._unit_of_work_factory() as uow:
                repo = self._auth_lockout_repository_factory(uow.session)
                record = repo.get_by_scope_key(key)
                if record is None:
                    record = AuthenticationLockout(
                        scope_key=key,
                        failed_count=1,
                        last_failed_at=now,
                        locked_until=None,
                    )
                else:
                    reset_window = (
                        record.last_failed_at is None
                        or record.locked_until is not None and record.locked_until <= now
                        or now - record.last_failed_at >= _LOCKOUT_DURATION
                    )
                    record.failed_count = 1 if reset_window else record.failed_count + 1
                    record.last_failed_at = now
                    record.locked_until = None

                if record.failed_count >= _MAX_FAILED_ATTEMPTS:
                    record.locked_until = now + _LOCKOUT_DURATION

                repo.save(record)
                uow.commit()
            return

        record = self._failed_attempts.get(key)
        now = datetime.utcnow()
        if record is None:
            self._failed_attempts[key] = (1, now)
        else:
            fail_count, last_failure = record
            # Reset counter if lockout period has fully elapsed
            if (now - last_failure) >= _LOCKOUT_DURATION:
                self._failed_attempts[key] = (1, now)
            else:
                self._failed_attempts[key] = (fail_count + 1, now)

    def _clear_failed_attempts(self, key: str) -> None:
        if self._auth_lockout_repository_factory is not None:
            with self._unit_of_work_factory() as uow:
                repo = self._auth_lockout_repository_factory(uow.session)
                repo.delete_by_scope_key(key)
                uow.commit()
            return

        self._failed_attempts.pop(key, None)

    # ── audit helper ─────────────────────────────────────────────────

    def _record_audit(
        self,
        company_id: int,
        event_type_code: str,
        entity_type: str,
        entity_id: int | None,
        description: str,
        detail_json: str | None = None,
    ) -> None:
        if self._audit_service is None:
            return
        try:
            self._audit_service.record_event(
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_type_code,
                    module_code=MODULE_AUTH,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    description=description,
                    detail_json=detail_json,
                ),
            )
        except Exception:  # noqa: BLE001 — audit must never break core auth flow
            pass

    def _require_permission_if_authenticated(self, permission_code: str) -> None:
        if self._permission_service.has_authenticated_actor():
            self._permission_service.require_permission(permission_code)
