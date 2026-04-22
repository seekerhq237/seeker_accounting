from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from seeker_accounting.config.paths import app_icon_path, ensure_runtime_directories, primary_logo_path
from seeker_accounting.config.settings import AppSettings
from seeker_accounting.platform.exceptions.app_exceptions import ConfigurationError

VALID_THEMES = {"light", "dark"}


@dataclass(frozen=True, slots=True)
class StartupCheckResult:
    created_directories: tuple[Path, ...]
    branding_logo_path: Path
    app_icon_path: Path


def run_startup_checks(settings: AppSettings) -> StartupCheckResult:
    if settings.theme_name not in VALID_THEMES:
        raise ConfigurationError(
            f"Unsupported theme '{settings.theme_name}'. Expected one of: {', '.join(sorted(VALID_THEMES))}."
        )

    created_directories = ensure_runtime_directories(settings.runtime_paths)
    logo_path = primary_logo_path()
    icon_path = app_icon_path()
    if not logo_path.exists():
        raise ConfigurationError(f"Branding logo asset was not found at: {logo_path}")
    if not icon_path.exists():
        raise ConfigurationError(f"Application icon asset was not found at: {icon_path}")

    if settings.database_url.startswith("sqlite:///"):
        settings.runtime_paths.database_file.parent.mkdir(parents=True, exist_ok=True)
    from seeker_accounting.db.migrations.init import ensure_database_schema
    ensure_database_schema(settings.database_url)

    # Initialize the trial timestamp on first run (no-op if already present).
    _initialize_trial_if_needed(settings)

    return StartupCheckResult(
        created_directories=created_directories,
        branding_logo_path=logo_path,
        app_icon_path=icon_path,
    )


def _initialize_trial_if_needed(settings: AppSettings) -> None:
    """Write trial.dat on first run.  Deferred import keeps startup fast."""
    try:
        from seeker_accounting.platform.licensing.license_service import LicenseService
        LicenseService(settings).initialize_trial_if_needed()
    except Exception:
        # Logging may not be set up yet; swallow silently.
        pass
