"""Permission checks for the current actor.

Reads from ``AppContext.permission_snapshot`` (the current user's effective
permission codes loaded at login time) and raises plain-English
``PermissionDeniedError`` messages when access is denied.
"""
from __future__ import annotations

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.modules.administration.rbac_catalog import SYSTEM_PERMISSION_BY_CODE
from seeker_accounting.platform.exceptions import PermissionDeniedError


class PermissionService:
    def __init__(self, app_context: AppContext) -> None:
        self._app_context = app_context

    @property
    def current_user_id(self) -> int | None:
        return self._app_context.current_user_id

    def has_authenticated_actor(self) -> bool:
        return self.current_user_id is not None

    def has_permission(self, permission_code: str) -> bool:
        return permission_code in self._app_context.permission_snapshot

    def has_any_permission(self, permission_codes: tuple[str, ...] | list[str]) -> bool:
        return any(self.has_permission(permission_code) for permission_code in permission_codes)

    def describe_permission(self, permission_code: str) -> str:
        definition = SYSTEM_PERMISSION_BY_CODE.get(permission_code)
        if definition is None:
            return "perform this action"
        description = definition.description.strip().rstrip(".")
        if not description:
            return "perform this action"
        return description[:1].lower() + description[1:]

    def build_denied_message(self, permission_code: str) -> str:
        return f"You do not have permission to {self.describe_permission(permission_code)}."

    def require_permission(self, permission_code: str) -> None:
        """Raise ``PermissionDeniedError`` if the current actor lacks the permission."""
        if self.has_permission(permission_code):
            return
        definition = SYSTEM_PERMISSION_BY_CODE.get(permission_code)
        raise PermissionDeniedError(
            self.build_denied_message(permission_code),
            context={
                "permission_code": permission_code,
                "permission_name": definition.name if definition is not None else permission_code,
                "permission_module": definition.module_code if definition is not None else None,
            },
        )

    def require_any_permission(self, permission_codes: tuple[str, ...] | list[str]) -> None:
        if self.has_any_permission(permission_codes):
            return
        primary_permission_code = permission_codes[0] if permission_codes else ""
        raise PermissionDeniedError(
            self.build_denied_message(primary_permission_code),
            context={
                "permission_codes": tuple(permission_codes),
            },
        )
