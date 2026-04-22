from __future__ import annotations

from seeker_accounting.platform.exceptions.app_exceptions import AppError


class LicenseLimitedError(AppError):
    """Raised when a write operation is attempted in read-only (unlicensed) mode."""

    def __init__(self, reason: str = "This action is not available in read-only mode.") -> None:
        super().__init__(reason)
