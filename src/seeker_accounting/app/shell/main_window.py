from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.command_palette import CommandPalette
from seeker_accounting.app.shell.command_palette_providers import (
    ActionsProvider,
    EntityProvider,
    NavigationProvider,
    ReportsProvider,
)
from seeker_accounting.app.shell.menu_bar import ShellMenuBar
from seeker_accounting.app.shell.readonly_banner import ReadOnlyBanner
from seeker_accounting.app.shell.ribbon import (
    RibbonActionDispatcher,
    RibbonBar,
    RibbonRegistry,
)
from seeker_accounting.app.shell.shell_models import PLACEHOLDER_PAGES
from seeker_accounting.app.shell.sidebar import ShellSidebar
from seeker_accounting.app.shell.status_bar import ShellStatusBar
from seeker_accounting.app.shell.topbar import ShellTopBar
from seeker_accounting.app.shell.workspace_host import WorkspaceHost
from seeker_accounting.config.constants import WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
from seeker_accounting.shared.ui.icon_provider import IconProvider


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service_registry = service_registry

        self.setWindowTitle(service_registry.settings.window_title)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        shell_root = QFrame(self)
        shell_root.setObjectName("ShellRoot")

        root_layout = QHBoxLayout(shell_root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = ShellSidebar(
            navigation_service=service_registry.navigation_service,
            active_company_context=service_registry.active_company_context,
            permission_service=service_registry.permission_service,
            company_logo_service=service_registry.company_logo_service,
            theme_manager=service_registry.theme_manager,
            parent=shell_root,
        )
        self._sidebar = sidebar
        root_layout.addWidget(sidebar)

        content_container = QWidget(shell_root)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._menu_bar = ShellMenuBar(
            service_registry=service_registry,
            show_command_palette=self._show_command_palette,
            toggle_sidebar=sidebar.toggle_collapsed,
            logout_requested=self.logout_requested.emit,
            parent=content_container,
        )
        content_layout.addWidget(self._menu_bar)

        topbar = ShellTopBar(
            service_registry=service_registry,
            toggle_sidebar=sidebar.toggle_collapsed,
            show_command_palette=self._show_command_palette,
            parent=self._menu_bar,
        )
        self._topbar = topbar
        sidebar.collapsed_changed.connect(topbar.set_sidebar_collapsed)
        topbar.set_sidebar_collapsed(sidebar.is_collapsed())
        topbar.logout_requested.connect(self.logout_requested.emit)
        self._menu_bar.setCornerWidget(topbar, Qt.Corner.TopRightCorner)

        self._readonly_banner = ReadOnlyBanner(content_container)
        self._readonly_banner.activate_requested.connect(self._show_license_dialog)
        content_layout.addWidget(self._readonly_banner)
        self._refresh_license_banner()

        # ── Sage-style context-aware ribbon ─────────────────────────
        self._ribbon_registry: RibbonRegistry = (
            service_registry.ribbon_registry or RibbonRegistry()
        )
        self._ribbon_dispatcher = RibbonActionDispatcher()
        self._ribbon_icon_provider = IconProvider(service_registry.theme_manager)
        self._ribbon_bar = RibbonBar(
            self._ribbon_registry,
            self._ribbon_icon_provider,
            self._ribbon_dispatcher,
            parent=content_container,
        )
        content_layout.addWidget(self._ribbon_bar)

        workspace_host = WorkspaceHost(
            service_registry=service_registry,
            parent=content_container,
        )
        self._workspace_host = workspace_host
        content_layout.addWidget(workspace_host, 1)

        self._status_bar = ShellStatusBar(service_registry=service_registry, parent=content_container)
        content_layout.addWidget(self._status_bar)

        root_layout.addWidget(content_container, 1)
        self.setCentralWidget(shell_root)

        service_registry.navigation_service.navigation_changed.connect(self._update_window_title)
        self._update_window_title(service_registry.navigation_service.current_nav_id)

        # Ribbon must re-target after every nav change. Use a queued hop so the
        # workspace host has time to materialize/swap the current page widget
        # before we ask it for the active IRibbonHost.
        service_registry.navigation_service.navigation_changed.connect(
            self._on_navigation_changed_for_ribbon
        )
        QTimer.singleShot(
            0,
            lambda: self._on_navigation_changed_for_ribbon(
                service_registry.navigation_service.current_nav_id
            ),
        )

        # ── Command palette (in-window overlay, child of shell_root) ──
        self._command_palette = CommandPalette(parent=shell_root)
        self._command_palette.set_providers([
            NavigationProvider(
                service_registry.navigation_service,
                service_registry.permission_service,
            ),
            ActionsProvider(service_registry.navigation_service, service_registry),
            ReportsProvider(
                service_registry.navigation_service,
                service_registry.permission_service,
            ),
            EntityProvider(service_registry),
        ])
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(self._show_command_palette)

    def _show_command_palette(self) -> None:
        self._command_palette.show_palette()

    def _update_window_title(self, nav_id: str) -> None:
        page = PLACEHOLDER_PAGES.get(nav_id)
        page_title = page.title if page else nav_id.replace("_", " ").title()
        self.setWindowTitle(f"{self._service_registry.settings.window_title} | {page_title}")

    def _on_navigation_changed_for_ribbon(self, nav_id: str) -> None:
        """Swap the ribbon surface to match the newly-active navigation page.

        The currently-visible page acts as the :class:`IRibbonHost`. If the
        page does not implement the host protocol (i.e. no ribbon_state /
        handle_ribbon_command methods yet), the surface is still shown but
        with default enablement and click-handlers are no-ops via the
        dispatcher's defensive guards.
        """

        self.refresh_current_ribbon_context(nav_id=nav_id)

    def refresh_current_ribbon_context(self, nav_id: str | None = None) -> None:
        """Recompute the active ribbon host and surface for the current page."""
        active_nav_id = nav_id or self._service_registry.navigation_service.current_nav_id
        if not active_nav_id:
            self._ribbon_bar.set_context(None)
            return

        page = self._workspace_host.current_page()
        host = self._resolve_ribbon_host(page)
        surface_key = self._resolve_ribbon_surface_key(active_nav_id, page, host)

        if surface_key and self._ribbon_registry.has(surface_key):
            self._ribbon_bar.set_context(surface_key, host)
            return
        if self._ribbon_registry.has(active_nav_id):
            self._ribbon_bar.set_context(active_nav_id, host)
            return
        self._ribbon_bar.set_context(None)

    @staticmethod
    def _is_ribbon_host(widget: object | None) -> bool:
        return (
            widget is not None
            and callable(getattr(widget, "handle_ribbon_command", None))
            and callable(getattr(widget, "ribbon_state", None))
        )

    def _resolve_ribbon_host(self, page: object | None) -> object | None:
        if page is None:
            return None
        current_host = getattr(page, "current_ribbon_host", None)
        if callable(current_host):
            try:
                resolved = current_host()
            except Exception:
                resolved = None
            if self._is_ribbon_host(resolved):
                return resolved
        if self._is_ribbon_host(page):
            return page
        return None

    @staticmethod
    def _resolve_ribbon_surface_key(
        nav_id: str,
        page: object | None,
        host: object | None,
    ) -> str:
        for candidate in (host, page):
            if candidate is None:
                continue
            getter = getattr(candidate, "current_ribbon_surface_key", None)
            if not callable(getter):
                continue
            try:
                surface_key = getter()
            except Exception:
                surface_key = None
            if surface_key:
                return str(surface_key)
        return nav_id

    def refresh_shell_context(self) -> None:
        self._sidebar.refresh_navigation_modules()
        self._topbar.refresh_context()
        self._status_bar.refresh()
        self._refresh_license_banner()

    def _refresh_license_banner(self) -> None:
        try:
            info = self._service_registry.license_service.get_license_info(bypass_cache=True)
            self._readonly_banner.refresh(info)
        except Exception:
            pass

    def _show_license_dialog(self) -> None:
        from seeker_accounting.app.shell.license_dialog import LicenseDialog
        LicenseDialog.show_modal(self._service_registry.license_service, parent=self)
        self._refresh_license_banner()
        self._topbar.refresh_context()

    def current_navigation_context(self) -> dict[str, object] | None:
        return self._workspace_host.get_last_navigation_context()

    def consume_current_resume_token(self) -> str | None:
        return self._workspace_host.consume_resume_token()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Prevent closing the shell while a user is logged in.

        The user must log out first so the session can be cleanly closed
        and audited.  If no user is logged in (e.g. the shell is being
        closed after a logout transferred control to the landing window),
        the close proceeds normally.
        """
        if self._service_registry.app_context.current_user_id is not None:
            event.ignore()
            self.logout_requested.emit()
        else:
            super().closeEvent(event)
