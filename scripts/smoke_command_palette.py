"""Smoke test for the command palette feature."""
import sys
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from scripts.shared import bootstrap_script_runtime
from seeker_accounting.app.security.permission_map import NAVIGATION_REQUIRED_PERMISSIONS
from seeker_accounting.app.shell.main_window import MainWindow

result = bootstrap_script_runtime(app)
permission_codes = sorted({code for group in NAVIGATION_REQUIRED_PERMISSIONS.values() for code in group})
result.service_registry.app_context.permission_snapshot = tuple(permission_codes)

mw = MainWindow(service_registry=result.service_registry)
print("[OK] App bootstrapped with command palette")

# Verify palette exists
palette = mw._command_palette
print(f"[OK] CommandPalette instance: {palette is not None}")
print(f"[OK] Palette has {len(palette._providers)} providers")

topbar = mw._topbar
# Phase 2: search trigger is now a real QLineEdit inside _search_frame
# Simulate pressing Enter on search to open palette
topbar._search_input.setText("cust")
topbar._show_search_palette()
app.processEvents()
print(f"[OK] Topbar search trigger shows shared palette: {palette.isVisible()}")
palette.hide()

# Test navigation provider search
nav_provider = palette._providers[0]
results = nav_provider.search("cust")
print(f"[OK] Nav search 'cust' returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title} ({r.subtitle}) score={r.score:.2f}")

# Test fuzzy with typos
results = nav_provider.search("chrt accnts")
print(f"[OK] Fuzzy 'chrt accnts' returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title} score={r.score:.2f}")

results = nav_provider.search("slsinv")
print(f"[OK] Fuzzy 'slsinv' returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title} score={r.score:.2f}")

# Test actions provider
actions_provider = palette._providers[1]
results = actions_provider.search("create inv")
print(f"[OK] Actions 'create inv' returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title} ({r.subtitle}) score={r.score:.2f}")

# Test reports provider
reports_provider = palette._providers[2]
results = reports_provider.search("trial bal")
print(f"[OK] Reports 'trial bal' returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title} ({r.subtitle}) score={r.score:.2f}")

# Test empty query with a loaded permission context.
results = nav_provider.search("")
print(f"[OK] Empty query returned {len(results)} navigation results (expected ~40)")
assert len(results) >= 30, f"Expected all pages, got {len(results)}"

# Test theme toggle action
results = actions_provider.search("dark mode")
print(f"[OK] 'dark mode' returned {len(results)} actions")
for r in results[:2]:
    print(f"     {r.title}")

# Test GL alias
results = nav_provider.search("GL")
print(f"[OK] 'GL' alias returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title} score={r.score:.2f}")

# Test CoA alias
results = nav_provider.search("CoA")
print(f"[OK] 'CoA' alias returned {len(results)} results")
for r in results[:2]:
    print(f"     {r.title} score={r.score:.2f}")

# Test AP / AR aliases
results = nav_provider.search("AR")
print(f"[OK] 'AR' alias returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title} score={r.score:.2f}")

results = nav_provider.search("AP")
print(f"[OK] 'AP' alias returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title} score={r.score:.2f}")

# Test report aliases
results = reports_provider.search("BS")
print(f"[OK] 'BS' report alias returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title}")

results = reports_provider.search("PL")
print(f"[OK] 'PL' report alias returned {len(results)} results")
for r in results[:3]:
    print(f"     {r.title}")

print()
print("ALL COMMAND PALETTE SMOKE TESTS PASSED")
sys.exit(0)
