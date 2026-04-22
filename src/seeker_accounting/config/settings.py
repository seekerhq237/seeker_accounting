from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from seeker_accounting.config import constants
from seeker_accounting.config.paths import PROJECT_ROOT, RuntimePaths, build_runtime_paths


@dataclass(frozen=True, slots=True)
class AppSettings:
    app_name: str
    organization_name: str
    window_title: str
    environment: str
    theme_name: str
    current_user_display_name: str
    runtime_paths: RuntimePaths
    database_url: str
    log_level: str


def load_settings() -> AppSettings:
    file_env = _load_project_env(PROJECT_ROOT / ".env")
    runtime_root_value = _get_env_value("SEEKER_RUNTIME_ROOT", file_env, "")
    runtime_paths = build_runtime_paths(Path(runtime_root_value).expanduser() if runtime_root_value else None)

    database_url = _get_env_value(
        "SEEKER_DATABASE_URL",
        file_env,
        f"sqlite:///{runtime_paths.database_file.as_posix()}",
    )

    return AppSettings(
        app_name=constants.APP_NAME,
        organization_name=constants.ORGANIZATION_NAME,
        window_title=constants.WINDOW_TITLE,
        environment=_get_env_value("SEEKER_ENV", file_env, constants.DEFAULT_ENVIRONMENT),
        theme_name=_get_env_value("SEEKER_THEME", file_env, constants.DEFAULT_THEME_NAME).lower(),
        current_user_display_name=_get_env_value(
            "SEEKER_CURRENT_USER",
            file_env,
            constants.DEFAULT_CURRENT_USER_DISPLAY_NAME,
        ),
        runtime_paths=runtime_paths,
        database_url=database_url,
        log_level=_get_env_value("SEEKER_LOG_LEVEL", file_env, constants.DEFAULT_LOG_LEVEL).upper(),
    )


def _get_env_value(name: str, file_env: dict[str, str], default: str) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    return file_env.get(name, default)


def _load_project_env(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        values[key.strip()] = raw_value.strip().strip("\"'")
    return values

