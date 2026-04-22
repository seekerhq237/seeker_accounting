"""Application exception package."""

from seeker_accounting.platform.exceptions.app_exceptions import (
    AppError,
    ConfigurationError,
    ConflictError,
    NavigationError,
    NotFoundError,
    PeriodLockedError,
    PermissionDeniedError,
    StartupError,
    ValidationError,
)
from seeker_accounting.platform.exceptions.app_error_codes import AppErrorCode
from seeker_accounting.platform.exceptions.error_resolution import (
    GuidedResolution,
    GuidedResolutionAction,
    GuidedResolutionSeverity,
    ResumeTokenPayload,
)
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver

__all__ = [
    "AppError",
    "ConfigurationError",
    "ConflictError",
    "NavigationError",
    "NotFoundError",
    "PeriodLockedError",
    "PermissionDeniedError",
    "StartupError",
    "ValidationError",
    "AppErrorCode",
    "GuidedResolution",
    "GuidedResolutionAction",
    "GuidedResolutionSeverity",
    "ResumeTokenPayload",
    "ErrorResolutionResolver",
]
