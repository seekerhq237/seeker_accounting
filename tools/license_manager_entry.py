"""Standalone entry point for the frozen (PyInstaller) license manager exe.

This file uses absolute imports so it works in both the frozen exe and
when run directly via ``python tools/license_manager_entry.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

# When running from source, ensure the project root is importable.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.license_manager.cli import main  # noqa: E402

main()
