from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
from seeker_accounting import __version__

from seeker_accounting.app.entry.landing_window import LandingWindow
from seeker_accounting.config.constants import WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
from seeker_accounting.config.paths import app_icon_path, primary_logo_path
from seeker_accounting.config.settings import AppSettings
from seeker_accounting.platform.exceptions.app_exceptions import StartupError

if TYPE_CHECKING:
    from seeker_accounting.app.context.app_context import AppContext
    from seeker_accounting.app.context.session_context import SessionContext
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry
    from seeker_accounting.app.entry.splash_screen import AnimatedSplashScreen
    from seeker_accounting.app.shell.main_window import MainWindow

logger = logging.getLogger(__name__)

VALID_THEMES = {"light", "dark"}


@dataclass(slots=True)
class BootstrapResult:
    settings: AppSettings
    landing_window: LandingWindow
    run_post_startup_tasks: Callable[[], None] | None = None



def bootstrap_application(
    qt_app: QApplication,
    *,
    settings: AppSettings,
    app_context: AppContext,
    session_context: SessionContext,
    initial_landing: AnimatedSplashScreen | None = None,
    defer_post_startup: bool = False,
) -> BootstrapResult:
    """Build the landing window and fully-initialized shell.

    All heavy work (DB, Alembic, module imports) has already been done
    by the background preloader.  This function creates the Qt-dependent
    objects (QObjects, QWidgets, shell) on the main thread.

    When *initial_landing* is provided it is the animated splash screen
    that has already transformed into an interactive landing surface.
    Its signals are wired below and a hidden LandingWindow is created
    for use after logout.
    """
    # ── Validate configuration ─────────────────────────────────────────
    if settings.theme_name not in VALID_THEMES:
        from seeker_accounting.platform.exceptions.app_exceptions import ConfigurationError
        raise ConfigurationError(
            f"Unsupported theme '{settings.theme_name}'. Expected one of: {', '.join(sorted(VALID_THEMES))}."
        )

    try:
        # ── Stage 1: Landing window + theming ──────────────────────────
        from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager

        logo_path = primary_logo_path()
        icon_path = app_icon_path()
        if not logo_path.exists():
            from seeker_accounting.platform.exceptions.app_exceptions import ConfigurationError
            raise ConfigurationError(f"Branding logo asset was not found at: {logo_path}")
        if not icon_path.exists():
            from seeker_accounting.platform.exceptions.app_exceptions import ConfigurationError
            raise ConfigurationError(f"Application icon asset was not found at: {icon_path}")

        theme_manager = ThemeManager(qt_app=qt_app, default_theme=settings.theme_name)
        theme_manager.apply_theme(settings.theme_name)

        app_icon = QIcon(str(icon_path))
        qt_app.setWindowIcon(app_icon)

        landing_window = LandingWindow(
            logo_path=logo_path,
            version_text=f"Version {__version__}",
            window_title=settings.window_title,
        )
        landing_window.setWindowIcon(app_icon)

        # ── Stage 2: Build shell eagerly (modules already cached) ──────
        service_registry, main_window = _build_shell(
            qt_app=qt_app,
            settings=settings,
            app_context=app_context,
            session_context=session_context,
            theme_manager=theme_manager,
            app_icon=app_icon,
            landing_window=landing_window,
        )

        # ── Wire landing-window signals (used after logout) ────────────
        landing_window.login_requested.connect(
            lambda: _handle_login(service_registry, main_window, landing_window)
        )
        landing_window.create_organisation_requested.connect(
            lambda: _handle_create_organisation(service_registry, main_window, landing_window)
        )
        landing_window.system_admin_requested.connect(
            lambda: _handle_system_admin(service_registry, landing_window)
        )
        landing_window.license_requested.connect(
            lambda: _handle_license(service_registry, landing_window)
        )
        landing_window.get_started_requested.connect(
            lambda: _handle_get_started(settings, landing_window)
        )

        # ── Wire initial-landing signals (splash-as-landing for first interaction) ──
        if initial_landing is not None:
            initial_landing.login_requested.connect(
                lambda: _handle_login_from_splash(service_registry, main_window, initial_landing)
            )
            initial_landing.create_organisation_requested.connect(
                lambda: _handle_create_organisation_from_splash(
                    service_registry, main_window, initial_landing, landing_window,
                )
            )
            initial_landing.system_admin_requested.connect(
                lambda: _handle_system_admin(service_registry, initial_landing)
            )
            initial_landing.license_requested.connect(
                lambda: _handle_license(service_registry, initial_landing)
            )
            initial_landing.get_started_requested.connect(
                lambda: _handle_get_started(settings, initial_landing)
            )

        # ── Post-startup tasks: purge check + Get Started guide ────────
        # These can pop modal dialogs, so they must only run once the
        # splash/landing surface is actually interactive. When
        # ``defer_post_startup`` is True the caller is responsible for
        # invoking ``result.run_post_startup_tasks`` at the appropriate
        # moment (after the splash signals ``ready_to_close``).
        from PySide6.QtCore import QTimer
        purge_parent: QWidget = initial_landing if initial_landing is not None else landing_window
        guide_parent: QWidget = initial_landing if initial_landing is not None else landing_window

        def _run_post_startup() -> None:
            QTimer.singleShot(100, lambda: _run_startup_purge_lightweight(session_context, purge_parent))
            QTimer.singleShot(400, lambda: _auto_show_get_started(settings, guide_parent))

        if not defer_post_startup:
            _run_post_startup()

    except Exception as exc:  # pragma: no cover - handled at process boundary
        logging.getLogger("seeker_accounting.bootstrap").exception("Bootstrap failed.")
        raise StartupError("Failed to initialize the Seeker Accounting application.") from exc

    logger.info("Seeker Accounting entry flow initialized.")
    return BootstrapResult(
        settings=settings,
        landing_window=landing_window,
        run_post_startup_tasks=_run_post_startup if defer_post_startup else None,
    )


def _build_shell(
    *,
    qt_app: QApplication,
    settings: AppSettings,
    app_context: AppContext,
    session_context: SessionContext,
    theme_manager: object,
    app_icon: QIcon,
    landing_window: LandingWindow,
) -> tuple[ServiceRegistry, MainWindow]:
    """Build the full shell: service registry + main window.

    All heavy module imports are already cached in sys.modules from the
    background preloader, so this executes quickly on the main thread.
    """
    from seeker_accounting.app.dependency.factories import (
        create_active_company_context,
        create_navigation_service,
        create_service_registry,
        create_session_idle_watcher_service,
    )
    from seeker_accounting.app.shell.main_window import MainWindow

    active_company_context = create_active_company_context(app_context)
    navigation_service = create_navigation_service()
    session_idle_watcher_service = create_session_idle_watcher_service(qt_app)

    service_registry = create_service_registry(
        settings=settings,
        app_context=app_context,
        session_context=session_context,
        active_company_context=active_company_context,
        navigation_service=navigation_service,
        theme_manager=theme_manager,
        session_idle_watcher_service=session_idle_watcher_service,
    )
    service_registry.reference_data_service.ensure_global_reference_data_seed()

    main_window = MainWindow(service_registry=service_registry)
    main_window.setWindowIcon(app_icon)

    # Wire shell-lifetime signals
    main_window.logout_requested.connect(
        lambda: _handle_logout(service_registry, landing_window, main_window)
    )
    session_idle_watcher_service.idle_logout_requested.connect(
        lambda: _handle_idle_logout(service_registry, landing_window, main_window)
    )
    active_company_context.active_company_changed.connect(
        lambda cid, _name: _on_active_company_changed(service_registry, cid)
    )

    return service_registry, main_window


def _run_startup_purge_lightweight(session_context: object, parent: QWidget) -> None:
    """Check for companies past their 30-day deletion window and purge them."""
    from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
    from seeker_accounting.modules.companies.services.company_purge_service import CompanyPurgeService

    purge_service = CompanyPurgeService(
        unit_of_work_factory=session_context.unit_of_work_factory,  # type: ignore[attr-defined]
        company_repository_factory=CompanyRepository,
    )
    try:
        due = purge_service.get_companies_due_for_purge()
        for dto in due:
            from seeker_accounting.modules.companies.ui.company_purge_export_dialog import (
                CompanyPurgeExportDialog,
            )

            CompanyPurgeExportDialog.confirm(dto.display_name, parent=parent)
            purge_service.permanently_purge_company(dto.id)
    except Exception:
        logger.exception("Startup company purge failed — skipping.")


def _open_shell_from_entry(landing_widget: QWidget, main_window: MainWindow) -> None:
    """Transfer from a landing surface (LandingWindow or splash) to the main shell."""
    main_window.refresh_shell_context()

    is_frameless = bool(landing_widget.windowFlags() & Qt.WindowType.FramelessWindowHint)

    if is_frameless:
        # Splash is a small frameless window — don't transfer its geometry.
        screen = landing_widget.screen()
        if screen is not None:
            avail = screen.availableGeometry()
            main_window.resize(
                min(avail.width(), WINDOW_MIN_WIDTH),
                min(avail.height(), WINDOW_MIN_HEIGHT),
            )
            frame = main_window.frameGeometry()
            frame.moveCenter(avail.center())
            main_window.move(frame.topLeft())
        main_window.show()
    elif landing_widget.isMaximized():
        main_window.showMaximized()
    elif landing_widget.isFullScreen():
        main_window.showFullScreen()
    else:
        main_window.setGeometry(landing_widget.geometry())
        main_window.show()

    main_window.raise_()
    main_window.activateWindow()
    landing_widget.close()


def _handle_login(
    service_registry: ServiceRegistry,
    main_window: MainWindow,
    landing_window: LandingWindow,
) -> None:
    """Show the login dialog, authenticate, load permissions, and open the shell."""
    from seeker_accounting.modules.administration.dto.user_commands import ChangePasswordCommand
    from seeker_accounting.modules.administration.ui.login_dialog import LoginDialog
    from seeker_accounting.modules.administration.ui.password_change_dialog import PasswordChangeDialog

    login_result = LoginDialog.prompt(
        company_service=service_registry.company_service,
        user_auth_service=service_registry.user_auth_service,
        parent=landing_window,
    )
    if login_result is None:
        return  # user cancelled

    if login_result.login_dto.must_change_password or login_result.login_dto.password_expired:
        password_result = PasswordChangeDialog.prompt(
            username=login_result.login_dto.username,
            allow_skip=False,
            parent=landing_window,
        )
        if password_result is None:
            return
        try:
            service_registry.user_auth_service.change_password(
                ChangePasswordCommand(
                    user_id=login_result.login_dto.user_id,
                    new_password=password_result.new_password,
                )
            )
            refreshed_login = service_registry.user_auth_service.complete_login(
                user_id=login_result.login_dto.user_id,
                company_id=login_result.company.id,
            )
            login_result = type(login_result)(
                login_dto=refreshed_login,
                company=login_result.company,
            )
        except Exception:
            logger.exception("Password change failed after login.")
            QMessageBox.warning(
                landing_window,
                "Password Change",
                "The password could not be changed. Please try logging in again.",
            )
            return

    _apply_login_to_context(service_registry, login_result)

    _handle_post_auth_session(service_registry, landing_window, login_result)

    _open_shell_from_entry(landing_window, main_window)


def _handle_login_from_splash(
    service_registry: ServiceRegistry,
    main_window: MainWindow,
    splash: AnimatedSplashScreen,
) -> None:
    """Login from the splash-landing surface; delegates to the shared login flow."""
    from seeker_accounting.modules.administration.dto.user_commands import ChangePasswordCommand
    from seeker_accounting.modules.administration.ui.login_dialog import LoginDialog
    from seeker_accounting.modules.administration.ui.password_change_dialog import PasswordChangeDialog

    login_result = LoginDialog.prompt(
        company_service=service_registry.company_service,
        user_auth_service=service_registry.user_auth_service,
        parent=splash,
    )
    if login_result is None:
        return

    if login_result.login_dto.must_change_password or login_result.login_dto.password_expired:
        password_result = PasswordChangeDialog.prompt(
            username=login_result.login_dto.username,
            allow_skip=False,
            parent=splash,
        )
        if password_result is None:
            return
        try:
            service_registry.user_auth_service.change_password(
                ChangePasswordCommand(
                    user_id=login_result.login_dto.user_id,
                    new_password=password_result.new_password,
                )
            )
            refreshed_login = service_registry.user_auth_service.complete_login(
                user_id=login_result.login_dto.user_id,
                company_id=login_result.company.id,
            )
            login_result = type(login_result)(
                login_dto=refreshed_login,
                company=login_result.company,
            )
        except Exception:
            logger.exception("Password change failed after login.")
            QMessageBox.warning(
                splash,
                "Password Change",
                "The password could not be changed. Please try logging in again.",
            )
            return

    _apply_login_to_context(service_registry, login_result)

    _handle_post_auth_session(service_registry, splash, login_result)

    _open_shell_from_entry(splash, main_window)


def _handle_create_organisation_from_splash(
    service_registry: ServiceRegistry,
    main_window: MainWindow,
    splash: AnimatedSplashScreen,
    landing_window: LandingWindow,
) -> None:
    """Create-organisation from splash; stays on splash (no shell transition)."""
    from seeker_accounting.app.dependency.factories import create_system_admin_service
    from seeker_accounting.modules.administration.ui.onboarding_coordinator import OnboardingCoordinator

    system_admin_service = create_system_admin_service(service_registry.session_context)

    if not _authorize_system_admin(system_admin_service, splash):
        return

    coordinator = OnboardingCoordinator(service_registry)
    result = coordinator.run(parent=splash)
    if result is None:
        return

    QMessageBox.information(
        splash,
        "Organisation Created",
        "The organisation has been created successfully.\n\n"
        f"Organisation: {result.company_name}\n"
        f"Admin username: {result.admin_username}\n\n"
        "Log in with the password you set to continue.",
    )


def _authorize_system_admin(
    system_admin_service: object,
    parent: QWidget,
) -> bool:
    from seeker_accounting.modules.companies.ui.system_admin_auth_dialog import SystemAdminAuthDialog
    from seeker_accounting.modules.companies.ui.system_admin_password_change_dialog import (
        SystemAdminPasswordChangeDialog,
    )

    if not system_admin_service.is_configured():
        SystemAdminPasswordChangeDialog.prompt(system_admin_service, parent)
        return system_admin_service.is_configured()

    authenticated = SystemAdminAuthDialog.authenticate(system_admin_service, parent)
    if not authenticated:
        return False

    if system_admin_service.must_change_password():
        SystemAdminPasswordChangeDialog.prompt(system_admin_service, parent)
        return system_admin_service.is_configured()

    return True


def _handle_post_auth_session(
    service_registry: ServiceRegistry,
    parent_widget: QWidget,
    login_result: object,
) -> None:
    """Detect abnormal previous sessions, start a new tracked session, and notify admins.

    Called after ``_apply_login_to_context()`` has populated ``app_context``.
    """
    user_id = login_result.login_dto.user_id
    company_id = login_result.company.id
    session_svc = service_registry.user_session_service

    # ── 1. Detect and resolve any unclosed (abnormal) previous sessions ─
    try:
        open_sessions = session_svc.check_abnormal_previous_sessions(user_id)
    except Exception:
        logger.warning("Failed to check for abnormal sessions.", exc_info=True)
        open_sessions = []

    if open_sessions:
        from seeker_accounting.modules.administration.ui.abnormal_shutdown_dialog import (
            AbnormalShutdownDialog,
        )

        result = AbnormalShutdownDialog.prompt(open_sessions, parent=parent_widget)
        if result is not None:
            explanation_code, explanation_note = result
            for s in open_sessions:
                try:
                    session_svc.resolve_abnormal_session(
                        s.id, explanation_code, explanation_note
                    )
                except Exception:
                    logger.warning(
                        "Failed to resolve abnormal session %d.", s.id, exc_info=True
                    )

    # ── 2. Start a new tracked session ─────────────────────────────────
    try:
        session_id = session_svc.start_session(user_id, company_id)
        service_registry.app_context.current_session_id = session_id
    except Exception:
        logger.warning("Failed to start tracked session.", exc_info=True)
        service_registry.app_context.current_session_id = None

    # ── 3. Admin notification for unreviewed abnormal sessions ──────────
    _check_admin_abnormal_notifications(service_registry, company_id, parent_widget)


def _check_admin_abnormal_notifications(
    service_registry: ServiceRegistry,
    company_id: int,
    parent_widget: QWidget,
) -> None:
    """If the current user has admin-level permissions, show unreviewed abnormal sessions."""
    perm = service_registry.app_context.permission_snapshot
    is_admin = "administration.audit.view" in perm or "administration.users.view" in perm
    if not is_admin:
        return

    session_svc = service_registry.user_session_service
    try:
        unreviewed = session_svc.get_unreviewed_abnormal_sessions_for_company(company_id)
    except Exception:
        logger.warning("Failed to load unreviewed abnormal sessions.", exc_info=True)
        return

    if not unreviewed:
        return

    from seeker_accounting.modules.administration.ui.admin_abnormal_session_dialog import (
        AdminAbnormalSessionDialog,
    )

    current_user_id = service_registry.app_context.current_user_id

    def _on_acknowledge(session_id: int) -> None:
        try:
            session_svc.mark_abnormal_reviewed(session_id, current_user_id)
        except Exception:
            logger.warning("Failed to mark session %d as reviewed.", session_id, exc_info=True)

    AdminAbnormalSessionDialog.prompt(
        unreviewed, on_acknowledge=_on_acknowledge, parent=parent_widget,
    )


def _apply_login_to_context(
    service_registry: ServiceRegistry,
    login_result: object,
) -> None:
    """Populate the authenticated user and active company contexts, start idle watcher."""
    ctx = service_registry.app_context
    ctx.current_user_id = login_result.login_dto.user_id
    ctx.current_user_display_name = login_result.login_dto.display_name
    ctx.permission_snapshot = login_result.login_dto.permission_codes

    try:
        service_registry.company_context_service.set_active_company(
            login_result.company.id,
            user_id=login_result.login_dto.user_id,
        )
    except Exception:
        # Roll back auth context so we don't leave a partial session.
        ctx.current_user_id = None
        ctx.current_user_display_name = ""
        ctx.permission_snapshot = ()
        raise

    _start_idle_watcher(service_registry, login_result.company.id)


def _handle_create_organisation(
    service_registry: ServiceRegistry,
    main_window: MainWindow,
    landing_window: LandingWindow,
) -> None:
    from seeker_accounting.app.dependency.factories import create_system_admin_service
    from seeker_accounting.modules.administration.ui.onboarding_coordinator import OnboardingCoordinator

    system_admin_service = create_system_admin_service(service_registry.session_context)

    if not _authorize_system_admin(system_admin_service, landing_window):
        return

    coordinator = OnboardingCoordinator(service_registry)
    result = coordinator.run(parent=landing_window)
    if result is None:
        return

    QMessageBox.information(
        landing_window,
        "Organisation Created",
        "The organisation has been created successfully.\n\n"
        f"Organisation: {result.company_name}\n"
        f"Admin username: {result.admin_username}\n\n"
        "Log in with the password you set to continue.",
    )


def _handle_logout(
    service_registry: ServiceRegistry,
    landing_window: LandingWindow,
    main_window: MainWindow,
) -> None:
    """Prompt for confirmation, then clear session state and return to the landing window."""
    answer = QMessageBox.question(
        main_window,
        "Log Out",
        "Are you sure you want to log out?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    _execute_logout(service_registry, landing_window, main_window)


def _handle_idle_logout(
    service_registry: ServiceRegistry,
    landing_window: LandingWindow,
    main_window: MainWindow,
) -> None:
    """Force logout after idle timeout — no confirmation prompt."""
    logger.info("Idle timeout reached — forcing logout.")
    _execute_logout(service_registry, landing_window, main_window, logout_reason="idle_timeout")


def _execute_logout(
    service_registry: ServiceRegistry,
    landing_window: LandingWindow,
    main_window: MainWindow,
    *,
    logout_reason: str = "normal",
) -> None:
    """Shared logout logic: stop watcher, end session, clear context, show the landing splash."""
    from seeker_accounting.app.navigation import nav_ids

    service_registry.session_idle_watcher_service.stop()

    # Close any open dialogs that are children of the main window.
    from PySide6.QtWidgets import QDialog
    for dialog in main_window.findChildren(QDialog):
        if dialog.isVisible():
            dialog.reject()

    # End the tracked session BEFORE clearing the context.
    ctx = service_registry.app_context
    try:
        service_registry.user_session_service.end_session(
            ctx.current_session_id, logout_reason
        )
    except Exception:
        logger.warning("Failed to end tracked session on logout.", exc_info=True)

    ctx.current_user_id = None
    ctx.current_user_display_name = ""
    ctx.permission_snapshot = ()
    ctx.current_session_id = None

    service_registry.active_company_context.clear_active_company()
    service_registry.navigation_service.navigate(nav_ids.DEFAULT_NAV_ID)

    # Show the animated splash in instant-landing mode so the user lands on
    # the new entry surface.  The old LandingWindow is kept alive — it is
    # still used as the hidden fallback wired at bootstrap.
    _show_splash_as_post_logout_landing(service_registry, main_window)


def _show_splash_as_post_logout_landing(
    service_registry: ServiceRegistry,
    main_window: MainWindow,
) -> None:
    """Create a fresh AnimatedSplashScreen, skip to landing state, wire signals,
    centre on the current screen, and close the main window."""
    from seeker_accounting.app.entry.splash_screen import AnimatedSplashScreen
    from seeker_accounting.config.paths import app_icon_path
    from PySide6.QtGui import QIcon

    splash = AnimatedSplashScreen()

    icon_path = app_icon_path()
    if icon_path.exists():
        splash.setWindowIcon(QIcon(str(icon_path)))

    # Wire the same entry signals as the initial splash.
    splash.login_requested.connect(
        lambda: _handle_login_from_splash(service_registry, main_window, splash)
    )
    splash.create_organisation_requested.connect(
        lambda: _handle_create_organisation_from_splash(
            service_registry, main_window, splash, None  # type: ignore[arg-type]
        )
    )
    splash.system_admin_requested.connect(
        lambda: _handle_system_admin(service_registry, splash)
    )

    splash.show_as_landing()
    splash.show()
    splash.raise_()
    splash.activateWindow()
    main_window.close()


def _start_idle_watcher(service_registry: ServiceRegistry, company_id: int) -> None:
    """Read the company's idle timeout preference and start the idle watcher."""
    try:
        prefs = service_registry.company_service.get_company_preferences(company_id)
        timeout_minutes = prefs.idle_timeout_minutes
    except Exception:
        logger.warning("Could not read idle timeout preference; using default 2 minutes.")
        timeout_minutes = 2
    service_registry.session_idle_watcher_service.start(timeout_minutes)


def _on_active_company_changed(service_registry: ServiceRegistry, company_id: int | None) -> None:
    """Update the idle watcher timeout when the active company changes."""
    watcher = service_registry.session_idle_watcher_service
    if company_id is None:
        return  # clearing context during logout — watcher already stopped
    try:
        prefs = service_registry.company_service.get_company_preferences(company_id)
        watcher.update_timeout(prefs.idle_timeout_minutes)
    except Exception:
        logger.warning("Could not refresh idle timeout after company switch.")


def _handle_license(
    service_registry: ServiceRegistry,
    parent: QWidget,
) -> None:
    """Open the license management dialog from a pre-login surface."""
    from seeker_accounting.app.shell.license_dialog import LicenseDialog
    LicenseDialog.show_modal(service_registry.license_service, parent=parent)


def _handle_get_started(
    settings: AppSettings,
    parent: QWidget,
) -> None:
    """Open the Get Started guide (manual trigger from help button)."""
    from seeker_accounting.app.entry.get_started_window import GetStartedWindow
    from seeker_accounting.config.app_state import mark_get_started_seen

    dont_show, action = GetStartedWindow.show_guide(parent)
    if dont_show:
        mark_get_started_seen(settings.runtime_paths.config)

    # Forward the chosen action back to the parent landing surface.
    if action == GetStartedWindow.ACTION_LOGIN:
        if hasattr(parent, "login_requested"):
            parent.login_requested.emit()
    elif action == GetStartedWindow.ACTION_CREATE_ORG:
        if hasattr(parent, "create_organisation_requested"):
            parent.create_organisation_requested.emit()


def _auto_show_get_started(
    settings: AppSettings,
    parent: QWidget,
) -> None:
    """Show the Get Started guide automatically on first launch."""
    from seeker_accounting.app.entry.get_started_window import GetStartedWindow

    try:
        action = GetStartedWindow.show_if_first_launch(settings.runtime_paths.config, parent)
    except Exception:
        logger.debug("Get Started auto-show skipped due to error.", exc_info=True)
        return

    if action == GetStartedWindow.ACTION_LOGIN:
        if hasattr(parent, "login_requested"):
            parent.login_requested.emit()
    elif action == GetStartedWindow.ACTION_CREATE_ORG:
        if hasattr(parent, "create_organisation_requested"):
            parent.create_organisation_requested.emit()


def _handle_system_admin(
    service_registry: ServiceRegistry,
    parent: QWidget,
) -> None:
    from seeker_accounting.app.dependency.factories import (
        create_system_admin_company_service,
        create_system_admin_service,
    )
    from seeker_accounting.modules.companies.ui.system_admin_dialog import SystemAdminDialog

    system_admin_service = create_system_admin_service(service_registry.session_context)
    if not _authorize_system_admin(system_admin_service, parent):
        return

    system_admin_company_service = create_system_admin_company_service(
        service_registry.session_context,
        company_context_service=service_registry.company_context_service,
        audit_service=service_registry.audit_service,
    )
    SystemAdminDialog.open_for(system_admin_company_service, parent)
