from __future__ import annotations

from typing import Any, Mapping


class AppError(Exception):
    """Base application error with optional structured context for guided handling."""

    def __init__(
        self,
        message: str = "",
        *,
        app_error_code: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self._app_error_code = app_error_code
        self._context = dict(context or {})

    @property
    def app_error_code(self) -> str | None:
        return self._app_error_code

    @property
    def context(self) -> dict[str, Any]:
        return dict(self._context)


class ConfigurationError(AppError):
    """Raised when runtime configuration is invalid."""


class StartupError(AppError):
    """Raised when the application cannot start safely."""


class NavigationError(AppError):
    """Raised for invalid navigation requests."""


class ValidationError(AppError):
    """Raised when user-provided data fails application validation."""


class NotFoundError(AppError):
    """Raised when an expected entity cannot be found."""


class ConflictError(AppError):
    """Raised when a requested write conflicts with existing data."""


class PermissionDeniedError(AppError):
    """Raised when the current actor is not allowed to perform an action."""


class PeriodLockedError(AppError):
    """Raised when a fiscal period is locked against ordinary changes or posting."""
