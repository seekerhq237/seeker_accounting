# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Seeker License Manager GUI.

Build with:
    .venv\\Scripts\\python.exe -m PyInstaller license_manager_gui.spec --noconfirm

Output: dist/seeker_license_manager_gui.exe  (single-file windowed exe)
"""
import sys
from pathlib import Path

block_cipher = None
PROJECT_ROOT = Path(SPECPATH)

a = Analysis(
    [str(PROJECT_ROOT / "tools" / "license_manager_gui_entry.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Bundle both PEM key files into _keys/ inside the frozen EXE.
        # The private key never needs to exist externally on the vendor's machine.
        # The ledger (license_ledger.json) stays external next to the EXE.
        (str(PROJECT_ROOT / "keys" / "seeker_license_private.pem"), "_keys"),
        (str(PROJECT_ROOT / "keys" / "seeker_license_public.pem"),  "_keys"),
    ],
    hiddenimports=[
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
        "cryptography.hazmat.primitives.serialization",
        "cryptography.hazmat.backends",
        "cryptography.hazmat.backends.openssl",
        "cryptography.hazmat.backends.openssl.backend",
        "cryptography.hazmat.bindings._rust",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "sqlalchemy",
        "alembic",
        "jinja2",
        "pytest",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="seeker_license_manager_gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # GUI app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    onefile=True,
)
