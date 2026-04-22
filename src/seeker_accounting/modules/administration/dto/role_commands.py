from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateRoleCommand:
    code: str
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateRoleCommand:
    role_id: int
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class AssignRolePermissionsCommand:
    role_id: int
    permission_ids: tuple[int, ...]
