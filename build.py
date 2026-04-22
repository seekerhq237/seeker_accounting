"""Build script for Seeker Accounting desktop application.

Usage:
    python build.py                    Build the application (onedir mode)
    python build.py --clean            Clean previous build artifacts first
    python build.py --installer        Build + create Windows installer
    python build.py --clean --installer  Full clean build with installer

Output:
    dist/SeekerAccounting/SeekerAccounting.exe
    dist/installer/SeekerAccountingSetup-<version>.exe  (with --installer)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_FILE = PROJECT_ROOT / "seeker_accounting.spec"
ISS_FILE = PROJECT_ROOT / "installer.iss"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
LOGO_PNG = PROJECT_ROOT / "src" / "seeker_accounting" / "app" / "logos" / "SeekerAccounting_000FE_blue.png"
LOGO_ICO = PROJECT_ROOT / "src" / "seeker_accounting" / "app" / "logos" / "SeekerAccounting.ico"

# Common Inno Setup install locations
_ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]


def generate_ico() -> None:
    """Convert the PNG app icon to .ico for the Windows executable."""
    if LOGO_ICO.exists():
        print(f"  Icon already exists: {LOGO_ICO}")
        return
    if not LOGO_PNG.exists():
        print(f"  Warning: PNG icon not found at {LOGO_PNG}, skipping .ico generation.")
        return
    try:
        from PIL import Image
        img = Image.open(LOGO_PNG)
        img.save(
            LOGO_ICO,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        print(f"  Generated icon: {LOGO_ICO}")
    except ImportError:
        print("  Warning: Pillow not installed. Install with 'pip install Pillow' to generate .ico.")
        print("  Building without a custom .exe icon.")


def clean() -> None:
    """Remove previous build artifacts."""
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            print(f"  Removing {d}")
            shutil.rmtree(d)


def build() -> int:
    """Run PyInstaller with the spec file."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        str(SPEC_FILE),
    ]
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def _find_iscc() -> Path | None:
    """Locate the Inno Setup command-line compiler."""
    # Check PATH first
    iscc_on_path = shutil.which("ISCC")
    if iscc_on_path:
        return Path(iscc_on_path)
    for candidate in _ISCC_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def build_installer() -> int:
    """Compile the Inno Setup script into a Windows installer."""
    iscc = _find_iscc()
    if iscc is None:
        print("  ERROR: Inno Setup not found.")
        print("  Install from https://jrsoftware.org/isdown.php or via:")
        print("    winget install JRSoftware.InnoSetup")
        return 1
    if not ISS_FILE.exists():
        print(f"  ERROR: Inno Setup script not found: {ISS_FILE}")
        return 1

    (DIST_DIR / "installer").mkdir(parents=True, exist_ok=True)
    cmd = [str(iscc), str(ISS_FILE)]
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Seeker Accounting executable")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts before building")
    parser.add_argument("--installer", action="store_true", help="Build Windows installer after PyInstaller")
    args = parser.parse_args()

    total_steps = 4 if args.installer else 3

    print("=== Seeker Accounting Build ===\n")

    if args.clean:
        print(f"[1/{total_steps}] Cleaning previous build...")
        clean()
    else:
        print(f"[1/{total_steps}] Skipping clean (use --clean to remove old artifacts)")

    print(f"[2/{total_steps}] Generating .ico icon...")
    generate_ico()

    print(f"[3/{total_steps}] Running PyInstaller...")
    rc = build()

    if rc == 0:
        output_dir = DIST_DIR / "SeekerAccounting"
        exe_path = output_dir / "SeekerAccounting.exe"
        print(f"\n  PyInstaller output: {output_dir}")
        print(f"  Executable:         {exe_path}")
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"  Exe size:           {size_mb:.1f} MB")
    else:
        print(f"\n=== Build FAILED (exit code {rc}) ===")
        return rc

    if args.installer:
        print(f"\n[4/{total_steps}] Building Windows installer...")
        rc = build_installer()
        if rc == 0:
            installer_dir = DIST_DIR / "installer"
            installers = list(installer_dir.glob("*.exe"))
            if installers:
                installer_path = installers[0]
                size_mb = installer_path.stat().st_size / (1024 * 1024)
                print(f"\n=== Installer built successfully ===")
                print(f"  Installer: {installer_path}")
                print(f"  Size:      {size_mb:.1f} MB")
            else:
                print(f"\n=== Installer built ===")
                print(f"  Output:    {installer_dir}")
        else:
            print(f"\n=== Installer build FAILED (exit code {rc}) ===")
            return rc
    else:
        print(f"\n=== Build successful ===")
        print(f"  (Use --installer to also create a Windows installer)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
