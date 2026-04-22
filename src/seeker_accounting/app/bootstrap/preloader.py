from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QThread, Signal

from seeker_accounting.config.settings import AppSettings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreloadResult:
    """Thread-safe resources produced by background preloading."""
    settings: AppSettings
    app_context: Any       # AppContext (dataclass — no Qt)
    session_context: Any   # SessionContext (frozen dataclass — no Qt)


class BackgroundPreloader(QThread):
    """Background thread that performs all heavyweight, thread-safe startup work.

    This caches 200+ Python module imports (via importing factories.py),
    initialises the database engine/session, runs Alembic migrations,
    and prepares AppContext/SessionContext — all before the user sees
    the landing window.

    All Qt object creation (QObject, QWidget, Signal owners) is deliberately
    excluded and must happen on the main thread after this finishes.
    """

    progress = Signal(str)
    finished_ok = Signal(object)   # emits PreloadResult
    failed = Signal(str)           # emits error message

    def __init__(self, settings: AppSettings, parent: QThread | None = None) -> None:
        super().__init__(parent)
        self._settings = settings

    def run(self) -> None:  # noqa: D401 — QThread override
        try:
            self._execute()
        except Exception as exc:
            logger.exception("Background preload failed.")
            self.failed.emit(str(exc))

    def _execute(self) -> None:
        settings = self._settings

        # ── 1. Startup checks (Alembic migration, directory creation) ──
        self.progress.emit("Checking database...")
        from seeker_accounting.app.bootstrap.startup_checks import run_startup_checks
        run_startup_checks(settings)

        # ── 2. Logging configuration ───────────────────────────────────
        from seeker_accounting.platform.logging.logging_config import configure_logging
        configure_logging(settings)

        # ── 3. Database engine + session factory ───────────────────────
        self.progress.emit("Initializing database...")
        from seeker_accounting.app.context.app_context import AppContext
        from seeker_accounting.app.context.session_context import SessionContext
        from seeker_accounting.db.engine import create_database_engine
        from seeker_accounting.db.session import create_session_factory
        from seeker_accounting.db.unit_of_work import create_unit_of_work_factory

        app_context = AppContext(
            current_user_id=None,
            current_user_display_name=settings.current_user_display_name,
            active_company_id=None,
            active_company_name=None,
            theme_name=settings.theme_name,
            permission_snapshot=tuple(),
        )
        engine = create_database_engine(settings)
        session_factory = create_session_factory(engine)
        unit_of_work_factory = create_unit_of_work_factory(session_factory)
        session_context = SessionContext(
            engine=engine,
            session_factory=session_factory,
            unit_of_work_factory=unit_of_work_factory,
        )

        # ── 4. Pre-import the heavyweight factories module ─────────────
        #    This is the single most expensive operation at startup:
        #    it cascades into 200+ module imports across the entire
        #    codebase. Once cached in sys.modules, all subsequent
        #    service construction is near-instant.
        self.progress.emit("Loading modules...")
        import seeker_accounting.app.dependency.factories  # noqa: F401

        # ── 5. Startup purge check (lightweight DB query) ──────────────
        self.progress.emit("Preparing workspace...")
        self._run_purge_check(session_context)

        # ── Done ───────────────────────────────────────────────────────
        result = PreloadResult(
            settings=settings,
            app_context=app_context,
            session_context=session_context,
        )
        self.finished_ok.emit(result)

    def _run_purge_check(self, session_context: object) -> None:
        """Check for companies due for purge — query only, no UI dialogs."""
        try:
            from seeker_accounting.modules.companies.repositories.company_repository import (
                CompanyRepository,
            )
            from seeker_accounting.modules.companies.services.company_purge_service import (
                CompanyPurgeService,
            )

            purge_service = CompanyPurgeService(
                unit_of_work_factory=session_context.unit_of_work_factory,  # type: ignore[attr-defined]
                company_repository_factory=CompanyRepository,
            )
            due = purge_service.get_companies_due_for_purge()
            if due:
                # Store for the main thread to handle after landing is visible
                self._purge_due = due
        except Exception:
            logger.exception("Startup purge check failed — skipping.")
