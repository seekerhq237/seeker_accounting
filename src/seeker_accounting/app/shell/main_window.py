from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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
from seeker_accounting.app.shell.shell_models import PLACEHOLDER_PAGES
from seeker_accounting.app.shell.sidebar import ShellSidebar
from seeker_accounting.app.shell.status_bar import ShellStatusBar
from seeker_accounting.app.shell.topbar import ShellTopBar
from seeker_accounting.app.shell.workspace_host import WorkspaceHost
from seeker_accounting.config.constants import WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH


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
            parent=content_container,
        )
        self._topbar = topbar
        sidebar.collapsed_changed.connect(topbar.set_sidebar_collapsed)
        topbar.set_sidebar_collapsed(sidebar.is_collapsed())
        topbar.logout_requested.connect(self.logout_requested.emit)
        content_layout.addWidget(topbar)

        self._readonly_banner = ReadOnlyBanner(content_container)
        self._readonly_banner.activate_requested.connect(self._show_license_dialog)
        content_layout.addWidget(self._readonly_banner)
        self._refresh_license_banner()

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
