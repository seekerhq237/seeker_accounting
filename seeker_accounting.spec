# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Seeker Accounting.

Build with:
    pyinstaller seeker_accounting.spec

Or use the build script:
    python build.py
"""
import os
import sys
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH)
SRC_ROOT = PROJECT_ROOT / "src"
PKG_ROOT = SRC_ROOT / "seeker_accounting"

# ---------------------------------------------------------------------------
# Locate the PySide6 package directory (in the venv used to build)
# ---------------------------------------------------------------------------
import PySide6 as _pyside6_pkg
_PYSIDE6_DIR = Path(_pyside6_pkg.__file__).parent

# ---------------------------------------------------------------------------
# Data files to bundle (source, destination-in-bundle)
# ---------------------------------------------------------------------------
datas = [
    # Alembic configuration
    (str(PROJECT_ROOT / "alembic.ini"), "."),

    # Alembic migrations (entire tree)
    (str(PKG_ROOT / "db" / "migrations"), os.path.join("seeker_accounting", "db", "migrations")),

    # Application logos
    (str(PKG_ROOT / "app" / "logos"), os.path.join("seeker_accounting", "app", "logos")),

    # Chart of accounts templates
    (str(PKG_ROOT / "resources" / "chart_templates"), os.path.join("seeker_accounting", "resources", "chart_templates")),

    # Sidebar SVG icons
    (str(PKG_ROOT / "resources" / "icons"), os.path.join("seeker_accounting", "resources", "icons")),

    # Reference data seed CSVs
    (str(PKG_ROOT / "modules" / "accounting" / "reference_data" / "seeds"), os.path.join("seeker_accounting", "modules", "accounting", "reference_data", "seeds")),
]

# ---------------------------------------------------------------------------
# WebEngine resource data files (.pak, icudtl.dat)
# These are not Python modules but are required at runtime by Chromium.
# ---------------------------------------------------------------------------
_WE_RESOURCE_NAMES = [
    "qtwebengine_resources.pak",
    "qtwebengine_resources_100p.pak",
    "qtwebengine_resources_200p.pak",
    "qtwebengine_devtools_resources.pak",
    "icudtl.dat",
]
_we_resources_dir = _PYSIDE6_DIR / "resources"
for _name in _WE_RESOURCE_NAMES:
    _p = _we_resources_dir / _name
    if _p.exists():
        datas.append((str(_p), os.path.join("PySide6", "resources")))

# WebEngine locale .pak files (Chromium i18n resources)
_we_locales_dir = _PYSIDE6_DIR / "translations" / "qtwebengine_locales"
if _we_locales_dir.exists():
    for _pak in _we_locales_dir.glob("*.pak"):
        datas.append((str(_pak), os.path.join("PySide6", "translations", "qtwebengine_locales")))

# ---------------------------------------------------------------------------
# Binaries: WebEngine executables (QtWebEngineProcess.exe) and DLLs
# ---------------------------------------------------------------------------
binaries = []

_WE_BINARY_NAMES = [
    "QtWebEngineProcess.exe",
    "Qt6WebEngineCore.dll",
    "Qt6WebEngineWidgets.dll",
    "Qt6WebChannel.dll",
]
for _bin_name in _WE_BINARY_NAMES:
    _bp = _PYSIDE6_DIR / _bin_name
    if _bp.exists():
        binaries.append((str(_bp), "PySide6"))


# ---------------------------------------------------------------------------
# Hidden imports that PyInstaller may miss
# ---------------------------------------------------------------------------
hiddenimports = [
    # SQLAlchemy dialects
    "sqlalchemy.dialects.sqlite",
    # Alembic internals
    "alembic",
    "alembic.config",
    "alembic.command",
    "alembic.runtime.migration",
    "alembic.ddl.impl",
    "alembic.ddl.sqlite",
    # bcrypt backend
    "bcrypt",
    "_bcrypt",
    # openpyxl / docx
    "openpyxl",
    "docx",
    # PySide6 modules
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport",
    # PySide6 WebEngine (Chromium-based rendering for PDF/preview)
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    # Compiled Qt resource module
    "seeker_accounting.resources.sidebar_icons_rc",
    # DB model registry (ensures all models are imported for Alembic)
    "seeker_accounting.db.model_registry",
    # Licensing subsystem (dynamically imported at runtime via lazy imports)
    "seeker_accounting.platform.licensing",
    "seeker_accounting.platform.licensing.key_validator",
    "seeker_accounting.platform.licensing.license_service",
    "seeker_accounting.platform.licensing.storage",
    "seeker_accounting.platform.licensing.dto",
    "seeker_accounting.platform.licensing.exceptions",
    "seeker_accounting.app.shell.license_dialog",
    "seeker_accounting.app.shell.license_chip",
    # cryptography backend for Ed25519 key validation
    "cryptography.hazmat.primitives.asymmetric.ed25519",
    "cryptography.hazmat.primitives.serialization",
    "cryptography.hazmat.backends",
    "cryptography.hazmat.backends.openssl",
    "cryptography.hazmat.backends.openssl.backend",
    "cryptography.hazmat.bindings._rust",
]

# ---------------------------------------------------------------------------
# Collect all migration version scripts dynamically
# ---------------------------------------------------------------------------
migration_versions_dir = PKG_ROOT / "db" / "migrations" / "versions"
for f in migration_versions_dir.glob("*.py"):
    module_name = f"seeker_accounting.db.migrations.versions.{f.stem}"
    if module_name not in hiddenimports:
        hiddenimports.append(module_name)

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(SRC_ROOT / "seeker_accounting" / "main.py")],
    pathex=[str(SRC_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "test",
        "pytest",
        "IPython",
        "notebook",
        "matplotlib",
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# Check for .ico version of the app icon; fall back to None
# ---------------------------------------------------------------------------
icon_path = str(PROJECT_ROOT / "src" / "seeker_accounting" / "app" / "logos" / "SeekerAccounting.ico")
if not os.path.isfile(icon_path):
    icon_path = None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SeekerAccounting",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SeekerAccounting",
)
