from __future__ import annotations

"""
LicenseService — evaluates and manages the license state of this installation.

This service is intentionally free of SQLAlchemy / SessionContext.  It reads
and writes flat files in the runtime config directory.
"""

import datetime
import logging

from seeker_accounting.config.settings import AppSettings
from seeker_accounting.platform.licensing.dto import LicenseInfo, LicenseState
from seeker_accounting.platform.licensing.exceptions import LicenseLimitedError
from seeker_accounting.platform.licensing.key_validator import LicenseKeyValidator, LicensePayload
from seeker_accounting.platform.licensing.storage import (
    StoredLicense,
    delete_license,
    read_license,
    read_trial_start,
    write_license,
    write_trial_start,
)

logger = logging.getLogger(__name__)

_TRIAL_DURATION_DAYS = 30


class LicenseService:
    """
    Evaluates the installation's license state and provides activation/deactivation.

    Usage
    -----
    * Call ``get_license_info()`` to get the current validated state.
    * Call ``activate_license(key)`` to validate and store a license key.
    * Call ``is_write_permitted()`` for a quick guard check in service layers.
    * Call ``ensure_write_permitted()`` to raise ``LicenseLimitedError`` if read-only.
    """

    def __init__(
        self,
        settings: AppSettings,
        validator: LicenseKeyValidator | None = None,
    ) -> None:
        self._config_dir = settings.runtime_paths.config
        self._validator = validator or LicenseKeyValidator()
        self._cached_info: LicenseInfo | None = None

    # ── Public API ────────────────────────────────────────────────────

    def get_license_info(self, *, bypass_cache: bool = False) -> LicenseInfo:
        """Return the current license state. Result is cached until invalidated."""
        if bypass_cache or self._cached_info is None:
            self._cached_info = self._evaluate()
        return self._cached_info

    def activate_license(self, key: str) -> LicenseInfo:
        """
        Validate *key* and persist it.

        Returns the new ``LicenseInfo`` on success.
        Raises ``ValueError`` with a user-facing message if the key is invalid.
        """
        payload: LicensePayload = self._validator.validate(key)

        today = datetime.date.today()
        if payload.expires_at < today:
            raise ValueError(
                f"This license key expired on {payload.expires_at.isoformat()}. "
                "Please obtain a renewed license key."
            )

        stored = StoredLicense(
            key=key.strip(),
            activated_at=today,
            expires_at=payload.expires_at,
            edition=payload.edition,
        )
        write_license(self._config_dir, stored)
        self._cached_info = None  # invalidate
        return self.get_license_info()

    def deactivate_license(self) -> LicenseInfo:
        """Remove the stored license and fall back to trial evaluation."""
        delete_license(self._config_dir)
        self._cached_info = None
        return self.get_license_info()

    def is_write_permitted(self) -> bool:
        """Return True if write operations are currently allowed."""
        return self.get_license_info().is_write_permitted

    def ensure_write_permitted(self) -> None:
        """
        Raise ``LicenseLimitedError`` if the installation is in read-only mode.

        Call this at the top of any service method that performs writes.
        """
        info = self.get_license_info()
        if not info.is_write_permitted:
            raise LicenseLimitedError(
                "Your license has expired. Please activate or renew your license to continue.\n\n"
                + info.summary
            )

    def initialize_trial_if_needed(self) -> None:
        """
        Write the trial.dat file if it does not yet exist.

        Must be called early in the startup sequence (after runtime dirs are created).
        """
        existing = read_trial_start(self._config_dir)
        if existing is None:
            now = datetime.datetime.now(tz=datetime.timezone.utc)
            write_trial_start(self._config_dir, now)
            logger.info("Trial started: %s", now.isoformat())

    # ── Internal evaluation ───────────────────────────────────────────

    def _evaluate(self) -> LicenseInfo:
        """Evaluate current state from files on disk."""
        today = datetime.date.today()

        # ── Try license key first ─────────────────────────────────────
        stored = read_license(self._config_dir)
        if stored is not None:
            try:
                # Re-validate key signature on every evaluation
                payload = self._validator.validate(stored.key)
                expires_at = payload.expires_at
            except ValueError:
                # Stored key is no longer valid (tampered or public key changed)
                logger.warning("Stored license key failed re-validation — treating as absent.")
                stored = None
                expires_at = None
            else:
                if expires_at >= today:
                    return LicenseInfo(
                        state=LicenseState.LICENSED_ACTIVE,
                        trial_days_remaining=0,
                        license_expires_at=expires_at,
                        summary=f"Licensed — expires {expires_at.isoformat()}",
                    )
                else:
                    return LicenseInfo(
                        state=LicenseState.LICENSED_EXPIRED,
                        trial_days_remaining=0,
                        license_expires_at=expires_at,
                        summary=(
                            f"License expired on {expires_at.isoformat()}. "
                            "Please renew your license to continue."
                        ),
                    )

        # ── Fall back to trial ────────────────────────────────────────
        trial_start = read_trial_start(self._config_dir)
        if trial_start is None:
            # Trial file missing — treat as expired (should have been written at startup)
            return LicenseInfo(
                state=LicenseState.TRIAL_EXPIRED,
                trial_days_remaining=0,
                license_expires_at=None,
                summary=(
                    "Your trial period has ended. "
                    "Please enter a license key to continue."
                ),
            )

        trial_start_date = trial_start.date() if isinstance(trial_start, datetime.datetime) else trial_start
        days_elapsed = (today - trial_start_date).days

        # Guard against clock roll-back: if trial_start is in the future, use today
        if days_elapsed < 0:
            days_elapsed = 0

        days_remaining = max(0, _TRIAL_DURATION_DAYS - days_elapsed)

        if days_remaining > 0:
            if days_remaining == 1:
                summary = "Trial — last day"
            else:
                summary = f"Trial — {days_remaining} days remaining"
            return LicenseInfo(
                state=LicenseState.TRIAL_ACTIVE,
                trial_days_remaining=days_remaining,
                license_expires_at=None,
                summary=summary,
            )
        else:
            return LicenseInfo(
                state=LicenseState.TRIAL_EXPIRED,
                trial_days_remaining=0,
                license_expires_at=None,
                summary=(
                    "Your 30-day trial has ended. "
                    "Please enter a license key to continue."
                ),
            )
