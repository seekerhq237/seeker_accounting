"""
Cryptographic operations for Seeker Accounting license keys.

Handles Ed25519 keypair generation, key signing, and key verification.
Completely standalone — does not import anything from the main application.
"""
from __future__ import annotations

import base64
import datetime
import os
import struct
from dataclasses import dataclass
from pathlib import Path

# ── Key format constants ──────────────────────────────────────────────────────
KEY_PREFIX = "SEEKER-"
_PAYLOAD_SIZE = 17
_SIGNATURE_SIZE = 64
_RAW_SIZE = _PAYLOAD_SIZE + _SIGNATURE_SIZE
_EDITION_STANDARD = 1


@dataclass(frozen=True, slots=True)
class LicensePayload:
    """Decoded contents of a validated license key."""
    edition: int
    issued_at: datetime.date
    expires_at: datetime.date


@dataclass(frozen=True, slots=True)
class KeypairPaths:
    """Paths to the generated keypair files."""
    private_key: Path
    public_key: Path
    public_key_hex: str


# ── Keypair generation ────────────────────────────────────────────────────────

def generate_keypair(out_dir: Path) -> KeypairPaths:
    """Generate a new Ed25519 keypair and write PEM files.

    Raises FileExistsError if the private key file already exists.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / "seeker_license_private.pem"
    public_path = out_dir / "seeker_license_public.pem"

    if private_path.exists():
        raise FileExistsError(
            f"Private key already exists at {private_path}.\n"
            "Delete it manually if you truly want to regenerate (this invalidates ALL existing keys)."
        )

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    public_raw = public_key.public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )

    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)

    return KeypairPaths(
        private_key=private_path,
        public_key=public_path,
        public_key_hex=public_raw.hex(),
    )


# ── License key signing ──────────────────────────────────────────────────────

def sign_license(
    private_key_path: Path,
    expiry_days: int,
    edition: int = _EDITION_STANDARD,
) -> tuple[str, datetime.date, datetime.date]:
    """Sign a new license key.

    Returns (key_string, issued_date, expires_date).
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    pem_data = private_key_path.read_bytes()
    private_key = load_pem_private_key(pem_data, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("The provided key is not an Ed25519 private key.")

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    expires = now + datetime.timedelta(days=expiry_days)

    issued_ts = int(now.timestamp())
    expires_ts = int(expires.timestamp())
    nonce = os.urandom(8)

    payload = struct.pack("!BII8s", edition, issued_ts, expires_ts, nonce)
    assert len(payload) == _PAYLOAD_SIZE

    signature = private_key.sign(payload)
    assert len(signature) == _SIGNATURE_SIZE

    raw = payload + signature
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{KEY_PREFIX}{encoded}", now.date(), expires.date()


# ── License key verification ─────────────────────────────────────────────────

def verify_license(key_string: str, public_key_path: Path) -> LicensePayload:
    """Verify a license key against the public key.

    Returns the decoded payload on success.
    Raises ValueError with a descriptive message on failure.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    key_string = key_string.strip()
    if not key_string.upper().startswith(KEY_PREFIX.upper()):
        raise ValueError("Invalid license key format — must start with 'SEEKER-'.")

    encoded = key_string[len(KEY_PREFIX):]
    try:
        padding = (4 - len(encoded) % 4) % 4
        raw = base64.urlsafe_b64decode(encoded + "=" * padding)
    except Exception:
        raise ValueError("License key contains invalid characters.")

    if len(raw) != _RAW_SIZE:
        raise ValueError(f"License key has unexpected length ({len(raw)} bytes, expected {_RAW_SIZE}).")

    payload_bytes = raw[:_PAYLOAD_SIZE]
    signature_bytes = raw[_PAYLOAD_SIZE:]

    pem_data = public_key_path.read_bytes()
    loaded_key = load_pem_public_key(pem_data)
    if not isinstance(loaded_key, Ed25519PublicKey):
        raise ValueError("The provided public key is not an Ed25519 public key.")

    try:
        loaded_key.verify(signature_bytes, payload_bytes)
    except Exception:
        raise ValueError("Signature verification FAILED — key is invalid, corrupted, or forged.")

    edition, issued_ts, expires_ts, _nonce = struct.unpack("!BII8s", payload_bytes)
    issued_at = datetime.date.fromtimestamp(issued_ts)
    expires_at = datetime.date.fromtimestamp(expires_ts)

    return LicensePayload(edition=edition, issued_at=issued_at, expires_at=expires_at)
