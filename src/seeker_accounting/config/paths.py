from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from seeker_accounting.config.constants import DATABASE_FILENAME

_FROZEN = getattr(sys, "frozen", False)

if _FROZEN:
    # PyInstaller: _MEIPASS is the temp extraction dir (onefile) or bundle dir (onedir)
    _BUNDLE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    PACKAGE_ROOT = _BUNDLE_DIR / "seeker_accounting"
    SRC_ROOT = _BUNDLE_DIR
    # PROJECT_ROOT = directory containing the .exe
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PACKAGE_ROOT = Path(__file__).resolve().parents[1]
    SRC_ROOT = PACKAGE_ROOT.parent
    PROJECT_ROOT = SRC_ROOT.parent

APP_LOGOS_ROOT = PACKAGE_ROOT / "app" / "logos"
PRIMARY_LOGO_FILENAME = "SeekerAccountingPrimaryLogo.png"
APP_ICON_FILENAME = "SeekerAccounting_000FE_blue.png"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    root: Path
    data: Path
    logs: Path
    config: Path
    database_file: Path


def default_runtime_root() -> Path:
    override = os.getenv("SEEKER_RUNTIME_ROOT")
    if override:
        return Path(override).expanduser()
    return PROJECT_ROOT / ".seeker_runtime"


def build_runtime_paths(root: Path | None = None) -> RuntimePaths:
    runtime_root = (root or default_runtime_root()).resolve()
    data_dir = runtime_root / "data"
    logs_dir = runtime_root / "logs"
    config_dir = runtime_root / "config"
    return RuntimePaths(
        root=runtime_root,
        data=data_dir,
        logs=logs_dir,
        config=config_dir,
        database_file=data_dir / DATABASE_FILENAME,
    )


def ensure_runtime_directories(runtime_paths: RuntimePaths) -> tuple[Path, ...]:
    created: list[Path] = []
    for path in (runtime_paths.root, runtime_paths.data, runtime_paths.logs, runtime_paths.config):
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
    return tuple(created)


def primary_logo_path() -> Path:
    return APP_LOGOS_ROOT / PRIMARY_LOGO_FILENAME


def app_icon_path() -> Path:
    return APP_LOGOS_ROOT / APP_ICON_FILENAME
