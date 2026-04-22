#!/usr/bin/env python3
"""
Generate an Ed25519 keypair for offline license signing.

Run ONCE and keep the private key file secure and offline.
Copy the printed PUBLIC_KEY_HEX into:
  src/seeker_accounting/platform/licensing/key_validator.py
as the value of _PUBLIC_KEY_BYTES.

Usage:
  python scripts/generate_license_keypair.py [--out-dir ./keys]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Ed25519 keypair for license signing.")
    parser.add_argument("--out-dir", default="./keys", help="Directory to write key files into.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = out_dir / "seeker_license_private.pem"
    public_key_path = out_dir / "seeker_license_public.pem"

    if private_key_path.exists():
        print(f"ERROR: Private key already exists at {private_key_path}")
        print("Delete it manually if you really want to regenerate.")
        sys.exit(1)

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )
    except ImportError:
        print("ERROR: 'cryptography' package is not installed. Run: pip install cryptography")
        sys.exit(1)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Serialize
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )

    # Write files
    private_key_path.write_bytes(private_pem)
    public_key_path.write_bytes(public_pem)

    # Extract raw 32-byte public key for embedding in key_validator.py
    raw_public_bytes = public_key.public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )
    public_hex = raw_public_bytes.hex()

    print("=" * 60)
    print("KEYPAIR GENERATED SUCCESSFULLY")
    print("=" * 60)
    print(f"Private key : {private_key_path}")
    print(f"Public key  : {public_key_path}")
    print()
    print("Embed the following in key_validator.py:")
    print("-" * 60)
    print(f'_PUBLIC_KEY_BYTES: bytes | None = bytes.fromhex(')
    print(f'    "{public_hex}"')
    print(')')
    print("-" * 60)
    print()
    print("KEEP THE PRIVATE KEY SAFE AND OFFLINE.")
    print("The public key hex is safe to embed in the application.")


if __name__ == "__main__":
    main()
