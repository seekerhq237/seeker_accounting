"""Phase 2 integration validation script."""
import sys
import tempfile
import pathlib

sys.argv = ["test"]

from seeker_accounting.shared.services.notification_center import NotificationCenter, AppNotification
from seeker_accounting.shared.services.sidebar_preferences_service import SidebarPreferencesService
from seeker_accounting.app.shell.status_bar import ShellStatusBar
from seeker_accounting.app.shell.topbar import ShellTopBar, _NotificationPanel
from seeker_accounting.app.shell.sidebar import ShellSidebar
from seeker_accounting.app.shell.main_window import MainWindow

# Test SidebarPreferencesService API with temp path
with tempfile.TemporaryDirectory() as td:
    sps = SidebarPreferencesService.__new__(SidebarPreferencesService)
    sps._path = pathlib.Path(td) / "prefs.json"
    sps._data = {"favorites": [], "recents": []}
    sps.add_favorite("journals")
    sps.add_favorite("sales_invoices")
    assert sps.is_favorite("journals"), "journals should be favorite"
    assert not sps.is_favorite("customers"), "customers should not be favorite"
    sps.push_recent("chart_of_accounts")
    sps.push_recent("journals")
    recents = sps.get_recents()
    assert recents[0] == "journals", f"Expected journals first, got {recents[0]}"
    assert len(sps.get_favorites()) == 2
    sps.remove_favorite("journals")
    assert not sps.is_favorite("journals")
    print("[OK] SidebarPreferencesService API")

# Test AppNotification structure
n = AppNotification(tone="warning", title="Test", body="Body text", nav_id="fiscal_periods")
assert n.tone == "warning"
assert n.nav_id == "fiscal_periods"
assert n.title == "Test"
print("[OK] AppNotification structure")

# Test QSS completeness
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS
from seeker_accounting.shared.ui.styles.qss_builder import build_stylesheet
from seeker_accounting.shared.ui.styles.palette import get_palette

required_selectors = [
    "NotificationPanel", "StatusBar", "SidebarNavBadge",
    "TopBarNewButton", "TopBarThemeToggle", "TopBarCompanySwitcher",
    "SidebarSearchInput", "SidebarSectionLabel", "TopBarBellButton",
    "NotificationRow", "NotificationTitle", "SidebarFavoriteButton",
    "SidebarRecentButton",
]
for theme_name in ("dark", "light"):
    palette = get_palette(theme_name)
    qss = build_stylesheet(palette, DEFAULT_TOKENS)
    for sel in required_selectors:
        assert sel in qss, f"Missing selector '{sel}' in {theme_name} theme"
print("[OK] QSS selectors (dark + light)")

print("\nPhase 2 integration check PASSED")
