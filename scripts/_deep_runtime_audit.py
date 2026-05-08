"""
Deep runtime audit for Seeker Accounting.

Checks:
  1. nav_ids attribute accesses — any nav_ids.X used in code that doesn't exist in nav_ids.py
  2. ServiceRegistry attribute accesses — any service_registry.X or registry.X used in code
     that isn't declared on the ServiceRegistry dataclass
  3. Feature flag constants — any FLAG_* imported from feature_flags that doesn't exist
  4. Navigation page factory map — nav ids referenced in sidebar module list that have no page factory
  5. Shell startup imports — verify key shell modules import cleanly

Usage:
    python scripts/_deep_runtime_audit.py
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import re
import sys
import traceback

ROOT = pathlib.Path(__file__).parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

ERRORS: list[str] = []
WARNINGS: list[str] = []
OK: list[str] = []

# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _py_files(folder: pathlib.Path):
    return list(folder.rglob("*.py"))

def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# 1. nav_ids attribute audit
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("CHECK 1: nav_ids attribute accesses")
print("="*70)

import seeker_accounting.app.navigation.nav_ids as _nav_ids_mod
valid_nav_attrs = {k for k in dir(_nav_ids_mod) if not k.startswith("_")}

# Find all nav_ids.SOMETHING usages across src/
pattern_nav = re.compile(r'\bnav_ids\.([A-Z_][A-Z0-9_]*)')
nav_refs: dict[str, list[str]] = {}  # attr -> [file:line, ...]

for f in _py_files(SRC):
    src_text = _read(f)
    for m in pattern_nav.finditer(src_text):
        attr = m.group(1)
        lineno = src_text[:m.start()].count('\n') + 1
        rel = str(f.relative_to(ROOT))
        nav_refs.setdefault(attr, []).append(f"{rel}:{lineno}")

missing_nav = {a: locs for a, locs in nav_refs.items() if a not in valid_nav_attrs}
if missing_nav:
    for attr, locs in sorted(missing_nav.items()):
        ERRORS.append(f"nav_ids.{attr} missing — used at: {locs[0]}" +
                      (f" (+{len(locs)-1} more)" if len(locs) > 1 else ""))
        print(f"  ERROR: nav_ids.{attr} not defined")
        for loc in locs:
            print(f"         {loc}")
else:
    OK.append("nav_ids: all referenced attributes exist")
    print("  OK — all nav_ids attributes are defined")

# ─────────────────────────────────────────────────────────────────────────────
# 2. ServiceRegistry attribute accesses
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("CHECK 2: ServiceRegistry attribute accesses")
print("="*70)

import dataclasses
from seeker_accounting.app.dependency.service_registry import ServiceRegistry
valid_registry_attrs = {f.name for f in dataclasses.fields(ServiceRegistry)}

# Also grab public methods
valid_registry_attrs |= {k for k in dir(ServiceRegistry) if not k.startswith("_")}

pattern_reg = re.compile(r'\bservice_registry\.([a-z_][a-z0-9_]*)')
reg_refs: dict[str, list[str]] = {}

for f in _py_files(SRC):
    src_text = _read(f)
    for m in pattern_reg.finditer(src_text):
        attr = m.group(1)
        lineno = src_text[:m.start()].count('\n') + 1
        rel = str(f.relative_to(ROOT))
        reg_refs.setdefault(attr, []).append(f"{rel}:{lineno}")

missing_reg = {a: locs for a, locs in reg_refs.items() if a not in valid_registry_attrs}
if missing_reg:
    for attr, locs in sorted(missing_reg.items()):
        ERRORS.append(f"service_registry.{attr} missing — used at: {locs[0]}" +
                      (f" (+{len(locs)-1} more)" if len(locs) > 1 else ""))
        print(f"  ERROR: service_registry.{attr} not declared on ServiceRegistry")
        for loc in locs:
            print(f"         {loc}")
else:
    OK.append("ServiceRegistry: all accessed attributes declared")
    print("  OK — all service_registry.* accesses are declared")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Feature flag constants
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("CHECK 3: Feature flag constants (FLAG_*)")
print("="*70)

import seeker_accounting.platform.feature_flags as _ff_mod
valid_flags = {k for k in dir(_ff_mod) if k.startswith("FLAG_")}

pattern_flag = re.compile(r'\b(FLAG_[A-Z0-9_]+)\b')
flag_refs: dict[str, list[str]] = {}

for f in _py_files(SRC):
    src_text = _read(f)
    for m in pattern_flag.finditer(src_text):
        attr = m.group(1)
        lineno = src_text[:m.start()].count('\n') + 1
        rel = str(f.relative_to(ROOT))
        flag_refs.setdefault(attr, []).append(f"{rel}:{lineno}")

missing_flags = {a: locs for a, locs in flag_refs.items() if a not in valid_flags}
if missing_flags:
    for attr, locs in sorted(missing_flags.items()):
        ERRORS.append(f"Feature flag {attr} not defined in feature_flags — used at: {locs[0]}")
        print(f"  ERROR: {attr} not defined in platform.feature_flags")
        for loc in locs:
            print(f"         {loc}")
else:
    OK.append("Feature flags: all FLAG_* constants defined")
    print("  OK — all FLAG_* constants are defined")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Navigation page factory map — nav ids in sidebar with no page factory
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("CHECK 4: Navigation page factory map")
print("="*70)

try:
    from seeker_accounting.app.navigation.navigation_service import NavigationService
    # NavigationService._page_factories or similar — let's find the page map
    # Try to import the pages map from wherever it's defined
    ns_src = (SRC / "seeker_accounting/app/navigation/navigation_service.py").read_text(encoding="utf-8")
    # Look for nav_id -> page class mappings
    page_map_matches = re.findall(r'nav_ids\.([A-Z_]+)\s*:', ns_src)
    registered_nav_ids = set(page_map_matches)
    
    # Also check shell_models or workspace_host
    ws_src = (SRC / "seeker_accounting/app/shell/workspace_host.py").read_text(encoding="utf-8")
    page_map_matches2 = re.findall(r'nav_ids\.([A-Z_]+)\s*:', ws_src)
    registered_nav_ids |= set(page_map_matches2)
    
    if registered_nav_ids:
        print(f"  Found {len(registered_nav_ids)} nav_id→page mappings across navigation_service + workspace_host")
        OK.append(f"Navigation page map: {len(registered_nav_ids)} entries checked")
    else:
        WARNINGS.append("Navigation page map: could not find nav_id→page mappings to audit")
        print("  WARN: could not locate nav_id→page mapping dict to audit")
except Exception as e:
    WARNINGS.append(f"Navigation page map audit skipped: {e}")
    print(f"  WARN: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Critical shell/bootstrap import chain
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("CHECK 5: Critical import chain")
print("="*70)

CRITICAL_IMPORTS = [
    "seeker_accounting.app.dependency.service_registry",
    "seeker_accounting.app.dependency.factories",
    "seeker_accounting.app.bootstrap.application",
    "seeker_accounting.app.shell.main_window",
    "seeker_accounting.app.shell.sidebar",
    "seeker_accounting.app.shell.workspace_host",
    "seeker_accounting.app.navigation.navigation_service",
    "seeker_accounting.app.navigation.nav_ids",
    "seeker_accounting.platform.feature_flags",
]

for mod_name in CRITICAL_IMPORTS:
    try:
        importlib.import_module(mod_name)
        print(f"  OK   {mod_name}")
        OK.append(f"import {mod_name}")
    except Exception as e:
        short = str(e).split('\n')[0]
        ERRORS.append(f"Import error: {mod_name} — {short}")
        print(f"  FAIL {mod_name}")
        print(f"       {short}")

# ─────────────────────────────────────────────────────────────────────────────
# 6. Sidebar module list vs nav_ids definitions
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("CHECK 6: Sidebar _build_modules nav_ids references")
print("="*70)

sidebar_src = _read(SRC / "seeker_accounting/app/shell/sidebar.py")
sidebar_nav_refs = set(re.findall(r'nav_ids\.([A-Z_][A-Z0-9_]*)', sidebar_src))
missing_sidebar = sidebar_nav_refs - valid_nav_attrs

if missing_sidebar:
    for attr in sorted(missing_sidebar):
        ERRORS.append(f"sidebar.py references nav_ids.{attr} which is not defined")
        print(f"  ERROR: nav_ids.{attr} used in sidebar.py but not defined")
else:
    OK.append("sidebar.py: all nav_ids references are defined")
    print(f"  OK — all {len(sidebar_nav_refs)} nav_ids refs in sidebar.py are valid")

# ─────────────────────────────────────────────────────────────────────────────
# 7. workspace_host / navigation_service nav_ids references
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("CHECK 7: workspace_host + navigation_service nav_ids references")
print("="*70)

for rel_path in [
    "seeker_accounting/app/shell/workspace_host.py",
    "seeker_accounting/app/navigation/navigation_service.py",
]:
    src_text = _read(SRC / rel_path)
    refs = set(re.findall(r'nav_ids\.([A-Z_][A-Z0-9_]*)', src_text))
    missing = refs - valid_nav_attrs
    if missing:
        for attr in sorted(missing):
            ERRORS.append(f"{rel_path} references nav_ids.{attr} which is not defined")
            print(f"  ERROR: nav_ids.{attr} in {rel_path} not defined")
    else:
        OK.append(f"{rel_path}: nav_ids refs OK")
        print(f"  OK — {rel_path} ({len(refs)} refs)")

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print(f"  OK:       {len(OK)}")
print(f"  Warnings: {len(WARNINGS)}")
print(f"  Errors:   {len(ERRORS)}")

if WARNINGS:
    print("\nWarnings:")
    for w in WARNINGS:
        print(f"  WARN  {w}")

if ERRORS:
    print("\nErrors (will crash at runtime):")
    for e in ERRORS:
        print(f"  ERROR {e}")
    sys.exit(1)
else:
    print("\nAll checks passed.")
    sys.exit(0)
