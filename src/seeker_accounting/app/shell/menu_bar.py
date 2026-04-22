"""Shell menu bar — Operational Desktop top menu band.

Thin, native-style QMenuBar that exposes the core application actions
as an always-visible band above the command band. All actions are
wired to existing services / navigation so this is a surface, not a
new command source.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenuBar, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation import nav_ids


class ShellMenuBar(QMenuBar):
    """Top menu band. File / Edit / View / Records / Reports / Tools / Help."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        *,
        show_command_palette: Callable[[], None] | None = None,
        toggle_sidebar: Callable[[], None] | None = None,
        logout_requested: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._show_command_palette = show_command_palette
        self._toggle_sidebar = toggle_sidebar
        self._logout_requested = logout_requested

        self.setObjectName("ShellMenuBar")
        self.setNativeMenuBar(False)

        self._build_file_menu()
        self._build_edit_menu()
        self._build_view_menu()
        self._build_records_menu()
        self._build_reports_menu()
        self._build_tools_menu()
        self._build_help_menu()

    # ── Menus ──────────────────────────────────────────────────────────

    def _build_file_menu(self) -> None:
        menu = self.addMenu("&File")
        menu.addAction(self._nav_action("Dashboard", nav_ids.DASHBOARD, "Ctrl+Home"))
        menu.addAction(self._nav_action("Companies", nav_ids.COMPANIES))
        menu.addSeparator()
        menu.addAction(self._nav_action("Backup and Restore", nav_ids.BACKUP_RESTORE))
        menu.addSeparator()
        logout = QAction("Sign &Out", self)
        logout.triggered.connect(self._emit_logout)
        menu.addAction(logout)
        quit_action = QAction("E&xit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self._quit_application)
        menu.addAction(quit_action)

    def _build_edit_menu(self) -> None:
        menu = self.addMenu("&Edit")
        find = QAction("&Find…", self)
        find.setShortcut(QKeySequence("Ctrl+F"))
        if self._show_command_palette is not None:
            find.triggered.connect(self._show_command_palette)
        else:
            find.setEnabled(False)
        menu.addAction(find)

    def _build_view_menu(self) -> None:
        menu = self.addMenu("&View")
        toggle = QAction("Toggle &Navigation", self)
        toggle.setShortcut(QKeySequence("Ctrl+B"))
        if self._toggle_sidebar is not None:
            toggle.triggered.connect(self._toggle_sidebar)
        else:
            toggle.setEnabled(False)
        menu.addAction(toggle)
        menu.addSeparator()
        theme = QAction("Switch &Theme", self)
        theme.triggered.connect(self._toggle_theme)
        menu.addAction(theme)

    def _build_records_menu(self) -> None:
        menu = self.addMenu("&Records")
        menu.addAction(self._nav_action("Customers", nav_ids.CUSTOMERS))
        menu.addAction(self._nav_action("Suppliers", nav_ids.SUPPLIERS))
        menu.addAction(self._nav_action("Chart of Accounts", nav_ids.CHART_OF_ACCOUNTS))
        menu.addAction(self._nav_action("Items", nav_ids.ITEMS))
        menu.addAction(self._nav_action("Fixed Assets", nav_ids.ASSETS))
        menu.addSeparator()
        menu.addAction(self._nav_action("Sales Invoices", nav_ids.SALES_INVOICES))
        menu.addAction(self._nav_action("Purchase Bills", nav_ids.PURCHASE_BILLS))
        menu.addAction(self._nav_action("Journals", nav_ids.JOURNALS))

    def _build_reports_menu(self) -> None:
        menu = self.addMenu("&Reports")
        menu.addAction(self._nav_action("Report Centre", nav_ids.REPORTS))

    def _build_tools_menu(self) -> None:
        menu = self.addMenu("&Tools")
        palette = QAction("Command &Palette…", self)
        palette.setShortcut(QKeySequence("Ctrl+K"))
        if self._show_command_palette is not None:
            palette.triggered.connect(self._show_command_palette)
        else:
            palette.setEnabled(False)
        menu.addAction(palette)
        menu.addSeparator()
        menu.addAction(self._nav_action("Administration", nav_ids.ADMINISTRATION))
        menu.addAction(self._nav_action("Roles", nav_ids.ROLES))
        menu.addAction(self._nav_action("Audit Log", nav_ids.AUDIT_LOG))
        menu.addAction(self._nav_action("Organisation Settings", nav_ids.ORGANISATION_SETTINGS))

    def _build_help_menu(self) -> None:
        menu = self.addMenu("&Help")
        about = QAction("&About Seeker Accounting", self)
        about.triggered.connect(self._show_about)
        menu.addAction(about)

    # ── Action helpers ────────────────────────────────────────────────

    def _nav_action(self, label: str, nav_id: str, shortcut: str | None = None) -> QAction:
        action = QAction(label, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False, target=nav_id: self._navigate(target))
        return action

    def _navigate(self, nav_id: str) -> None:
        try:
            self._sr.navigation_service.navigate(nav_id)
        except Exception:
            # Nav errors surface through the standard nav flow; menu must not crash.
            pass

    def _emit_logout(self) -> None:
        if self._logout_requested is not None:
            self._logout_requested()

    def _quit_application(self) -> None:
        window = self.window()
        if window is not None:
            window.close()

    def _toggle_theme(self) -> None:
        try:
            self._sr.theme_manager.toggle_theme()
        except Exception:
            pass

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        settings = self._sr.settings
        QMessageBox.about(
            self.window(),
            "About",
            f"<b>{settings.window_title}</b><br>Seeker Accounting.",
        )
