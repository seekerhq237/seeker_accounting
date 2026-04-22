from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UserDTO:
    id: int
    username: str
    display_name: str
    email: str | None
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    avatar_storage_path: str | None = None


@dataclass(frozen=True, slots=True)
class LoginResultDTO:
    user_id: int
    username: str
    display_name: str
    must_change_password: bool
    permission_codes: tuple[str, ...]
    password_expired: bool = False


@dataclass(frozen=True, slots=True)
class AuthenticatedUserDTO:
    user_id: int
    username: str
    display_name: str
    must_change_password: bool


@dataclass(frozen=True, slots=True)
class RoleDTO:
    id: int
    code: str
    name: str
    description: str | None
    is_system: bool


@dataclass(frozen=True, slots=True)
class PermissionDTO:
    id: int
    code: str
    name: str
    module_code: str
    description: str | None


@dataclass(frozen=True, slots=True)
class RoleWithPermissionsDTO:
    role: RoleDTO
    permissions: tuple[PermissionDTO, ...]


@dataclass(frozen=True, slots=True)
class UserWithRolesDTO:
    user: UserDTO
    roles: tuple[RoleDTO, ...]
