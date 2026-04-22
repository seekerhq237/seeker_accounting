"""
Lightweight JSON-backed application state persistence.

Stores ephemeral UI state (e.g. "has the user seen the Get Started guide?")
in `app_state.json` under the runtime config directory.

This is intentionally separate from trial.dat / license.dat — those track
licensing state with HMAC integrity.  This file tracks casual UI flags
that do not need tamper-evidence.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_FILENAME = "app_state.json"
_KEY_GET_STARTED_SEEN = "get_started_seen"


def _state_path(config_dir: Path) -> Path:
    return config_dir / _STATE_FILENAME


def read_app_state(config_dir: Path) -> dict:
    """Read the app state dict.  Returns ``{}`` if the file is missing or corrupt."""
    path = _state_path(config_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read %s — returning empty state.", path)
        return {}


def write_app_state(config_dir: Path, state: dict) -> None:
    """Atomically write the app state dict."""
    config_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(config_dir)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    shutil.move(str(tmp), str(path))


def has_seen_get_started(config_dir: Path) -> bool:
    return bool(read_app_state(config_dir).get(_KEY_GET_STARTED_SEEN, False))


def mark_get_started_seen(config_dir: Path) -> None:
    state = read_app_state(config_dir)
    state[_KEY_GET_STARTED_SEEN] = True
    write_app_state(config_dir, state)
