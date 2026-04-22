from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtWidgets import QApplication

from seeker_accounting.app.context.active_company_context import ActiveCompanyContext
from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.app.context.session_context import SessionContext
from seeker_accounting.app.dependency.factories import (
    create_active_company_context,
    create_app_context,
    create_navigation_service,
    create_service_registry,
    create_session_context,
    create_session_idle_watcher_service,
    create_theme_manager,
)
from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.navigation.navigation_service import NavigationService
from seeker_accounting.config.settings import AppSettings, load_settings
from seeker_accounting.platform.session.session_idle_watcher_service import SessionIdleWatcherService
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager


@dataclass(frozen=True, slots=True)
class ScriptBootstrap:
    qt_app: QApplication
    settings: AppSettings
    app_context: AppContext
    session_context: SessionContext
    active_company_context: ActiveCompanyContext
    navigation_service: NavigationService
    theme_manager: ThemeManager
    session_idle_watcher_service: SessionIdleWatcherService
    service_registry: ServiceRegistry


def bootstrap_script_runtime(
    qt_app: QApplication | None = None,
    *,
    permission_snapshot: Iterable[str] | None = None,
) -> ScriptBootstrap:
    """Build a fully wired runtime used by smoke and utility scripts.

    Keeps script bootstrap aligned with production bootstrap wiring so
    create_service_registry dependency changes are absorbed in one place.
    """
    app = qt_app or QApplication.instance() or QApplication([])
    settings = load_settings()
    app_context = create_app_context(settings)
    if permission_snapshot is not None:
        app_context.permission_snapshot = tuple(permission_snapshot)

    session_context = create_session_context(settings)
    active_company_context = create_active_company_context(app_context)
    navigation_service = create_navigation_service()
    theme_manager = create_theme_manager(app, settings, app_context)
    session_idle_watcher_service = create_session_idle_watcher_service(app)

    service_registry = create_service_registry(
        settings=settings,
        app_context=app_context,
        session_context=session_context,
        active_company_context=active_company_context,
        navigation_service=navigation_service,
        theme_manager=theme_manager,
        session_idle_watcher_service=session_idle_watcher_service,
    )
    return ScriptBootstrap(
        qt_app=app,
        settings=settings,
        app_context=app_context,
        session_context=session_context,
        active_company_context=active_company_context,
        navigation_service=navigation_service,
        theme_manager=theme_manager,
        session_idle_watcher_service=session_idle_watcher_service,
        service_registry=service_registry,
    )
