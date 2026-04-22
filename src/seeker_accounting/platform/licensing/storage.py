from __future__ import annotations

"""
Reads and writes the trial and license state files under
  .seeker_runtime/config/trial.dat
  .seeker_runtime/config/license.dat

File format (both files): JSON with an HMAC-SHA256 integrity field.

trial.dat:
  {
    "first_run": "2026-04-02T10:00:00+00:00",   # ISO datetime (UTC)
    "hmac": "<hex>"
  }

license.dat:
  {
    "key": "SEEKER-...",
    "activated_at": "2026-04-02",    # ISO date
    "expires_at": "2027-04-02",      # ISO date
    "edition": 1,
    "hmac": "<hex>"
  }

The HMAC key is derived from:
  SHA-256( _HMAC_PEPPER + config_dir_path_as_bytes )

This is not cryptographically strong machine-binding — the files could
theoretically be copied with the config directory path known — but it
provides a lightweight tamper-evidence layer without a server.
"""

import datetime
import hashlib
import hmac
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_HMAC_PEPPER = b"seeker-accounting-v1-license-integrity-guard"


def _derive_hmac_key(config_dir: Path) -> bytes:
    path_bytes = str(config_dir.resolve()).encode("utf-8")
    return hashlib.sha256(_HMAC_PEPPER + path_bytes).digest()


def _sign(payload: dict, hmac_key: bytes) -> str:
    """Return HMAC-SHA256 hex of the canonical payload (excludes 'hmac' field)."""
    canonical = {k: v for k, v in sorted(payload.items()) if k != "hmac"}
    message = json.dumps(canonical, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hmac.new(hmac_key, message, hashlib.sha256).hexdigest()


def _verify(payload: dict, hmac_key: bytes) -> bool:
    stored_mac = payload.get("hmac", "")
    expected = _sign(payload, hmac_key)
    return hmac.compare_digest(stored_mac, expected)


# ── Trial file ────────────────────────────────────────────────────────────────

def read_trial_start(config_dir: Path) -> datetime.datetime | None:
    """Return the stored first-run datetime (UTC-aware), or None if absent / corrupt."""
    trial_file = config_dir / "trial.dat"
    if not trial_file.exists():
        return None
    try:
        data = json.loads(trial_file.read_text(encoding="utf-8"))
        hmac_key = _derive_hmac_key(config_dir)
        if not _verify(data, hmac_key):
            logger.warning("trial.dat HMAC mismatch — treating as absent.")
            return None
        return datetime.datetime.fromisoformat(data["first_run"])
    except Exception:
        logger.warning("Could not read trial.dat — treating as absent.")
        return None


def write_trial_start(config_dir: Path, first_run: datetime.datetime) -> None:
    """Write a new trial.dat with HMAC integrity."""
    trial_file = config_dir / "trial.dat"
    hmac_key = _derive_hmac_key(config_dir)
    payload: dict = {"first_run": first_run.isoformat()}
    payload["hmac"] = _sign(payload, hmac_key)
    trial_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ── License file ──────────────────────────────────────────────────────────────

class StoredLicense:
    __slots__ = ("key", "activated_at", "expires_at", "edition")

    def __init__(
        self,
        *,
        key: str,
        activated_at: datetime.date,
        expires_at: datetime.date,
        edition: int,
    ) -> None:
        self.key = key
        self.activated_at = activated_at
        self.expires_at = expires_at
        self.edition = edition


def read_license(config_dir: Path) -> StoredLicense | None:
    """Return the stored license, or None if absent / corrupt."""
    license_file = config_dir / "license.dat"
    if not license_file.exists():
        return None
    try:
        data = json.loads(license_file.read_text(encoding="utf-8"))
        hmac_key = _derive_hmac_key(config_dir)
        if not _verify(data, hmac_key):
            logger.warning("license.dat HMAC mismatch — treating as absent.")
            return None
        return StoredLicense(
            key=data["key"],
            activated_at=datetime.date.fromisoformat(data["activated_at"]),
            expires_at=datetime.date.fromisoformat(data["expires_at"]),
            edition=int(data.get("edition", 1)),
        )
    except Exception:
        logger.warning("Could not read license.dat — treating as absent.")
        return None


def write_license(config_dir: Path, stored: StoredLicense) -> None:
    """Persist a license record with HMAC integrity."""
    license_file = config_dir / "license.dat"
    hmac_key = _derive_hmac_key(config_dir)
    payload: dict = {
        "key": stored.key,
        "activated_at": stored.activated_at.isoformat(),
        "expires_at": stored.expires_at.isoformat(),
        "edition": stored.edition,
    }
    payload["hmac"] = _sign(payload, hmac_key)
    license_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def delete_license(config_dir: Path) -> None:
    """Remove the license.dat file (deactivation)."""
    license_file = config_dir / "license.dat"
    if license_file.exists():
        license_file.unlink()
