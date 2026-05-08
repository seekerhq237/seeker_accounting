from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QMessageBox

from seeker_accounting.config.constants import APP_NAME, ORGANIZATION_NAME

# ── Enable faulthandler immediately: catches C-level segfaults / aborts ──────
# Directed to stderr here; redirected to a real log file once the log directory
# is known (see _redirect_faulthandler_to_file below).
faulthandler.enable()


def _install_crash_hooks(logger: logging.Logger) -> None:
    """Install Python, threading, and Qt crash/exception reporters.

    Must be called once, after QApplication exists, before any heavy work.
    """

    def _excepthook(exc_type, exc_value, exc_tb):  # type: ignore[no-untyped-def]
        # Let KeyboardInterrupt use the normal handler (allows Ctrl+C).
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Unhandled exception on main thread",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        try:
            app = QApplication.instance()
            if app is not None:
                QMessageBox.critical(
                    None,
                    APP_NAME,
                    f"An unexpected error occurred.\n\n"
                    f"{exc_type.__name__}: {exc_value}\n\n"
                    "The error has been logged. If this keeps happening, contact support.",
                )
        except Exception:  # noqa: BLE001 — last-resort handler
            pass

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is None or issubclass(args.exc_type, SystemExit):
            return
        thread_name = getattr(args.thread, "name", "unknown-thread")
        logger.critical(
            "Unhandled exception in thread '%s'",
            thread_name,
            exc_info=(args.exc_type, args.exc_value, args.exc_tb),
        )

    def _qt_message_handler(mode: QtMsgType, _context: object, message: str) -> None:
        _levels = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }
        logger.log(_levels.get(mode, logging.DEBUG), "Qt: %s", message)

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    qInstallMessageHandler(_qt_message_handler)


def _redirect_faulthandler_to_file() -> None:
    """Point faulthandler at a persistent crash log once the log directory is known."""
    try:
        from seeker_accounting.config.paths import build_runtime_paths
        runtime = build_runtime_paths()
        runtime.logs.mkdir(parents=True, exist_ok=True)
        crash_path = runtime.logs / "crash.log"
        crash_file = open(crash_path, "ab")  # noqa: WPS515 — kept open by faulthandler
        faulthandler.enable(file=crash_file)
    except Exception:  # noqa: BLE001 — fall back to stderr, already enabled above
        pass


def main() -> int:
    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setApplicationName(APP_NAME)
    qt_app.setOrganizationName(ORGANIZATION_NAME)
    qt_app.setStyle("Fusion")
    qt_app.setQuitOnLastWindowClosed(True)

    # ── Install crash safety net (excepthooks + Qt message handler) ───
    _install_crash_hooks(logging.getLogger("seeker_accounting"))
    # Redirect faulthandler to the user's log dir as soon as paths are resolvable.
    _redirect_faulthandler_to_file()

    # ── Show animated splash immediately — before any heavy imports ────
    from seeker_accounting.config.settings import load_settings
    from seeker_accounting.app.entry.splash_screen import AnimatedSplashScreen

    splash = AnimatedSplashScreen()
    splash.show()
    splash.start_animation()
    qt_app.processEvents()

    # ── Load settings and start background preloader ───────────────────
    try:
        settings = load_settings()
    except Exception as exc:
        splash.close()
        logging.getLogger("seeker_accounting").exception("Failed to load settings.")
        QMessageBox.critical(None, APP_NAME, f"Application startup failed.\n\n{exc}")
        return 1

    from seeker_accounting.app.bootstrap.preloader import BackgroundPreloader

    preloader = BackgroundPreloader(settings)
    _preload_error = [None]   # mutable container for closure
    _bootstrap_result = [None]  # mutable container for closure

    def _on_preload_done(result: object) -> None:
        # ── Build the shell IMMEDIATELY on the main thread. ───────────
        # This must happen before the splash reports "ready" so that by
        # the time the landing buttons become interactive, the full
        # MainWindow shell is already constructed and clicks work
        # without a frozen-UI delay. Shell construction blocks the main
        # thread briefly (it can only run here), but it overlaps with
        # the tail of the splash animation rather than happening after
        # the buttons appear enabled — which is the UX we want.
        try:
            from seeker_accounting.app.bootstrap.application import bootstrap_application
            from seeker_accounting import __version__

            splash.set_version_text(f"Version {__version__}")

            _bootstrap_result[0] = bootstrap_application(
                qt_app=qt_app,
                settings=result.settings,
                app_context=result.app_context,
                session_context=result.session_context,
                initial_landing=splash,
                defer_post_startup=True,
            )
        except Exception as exc:
            splash.close()
            logging.getLogger("seeker_accounting").exception("Application startup failed.")
            QMessageBox.critical(None, APP_NAME, f"Application startup failed.\n\n{exc}")
            qt_app.quit()
            return

        splash.mark_preload_done()

    def _on_preload_failed(error_msg: str) -> None:
        _preload_error[0] = error_msg
        splash.mark_preload_failed(error_msg)

    preloader.progress.connect(splash.set_status)
    preloader.finished_ok.connect(_on_preload_done)
    preloader.failed.connect(_on_preload_failed)

    # ── When splash animation settles, run deferred post-startup tasks ──
    def _on_splash_ready() -> None:
        if _preload_error[0] is not None:
            splash.close()
            logging.getLogger("seeker_accounting").error(
                "Background preload failed: %s", _preload_error[0]
            )
            QMessageBox.critical(
                None, APP_NAME,
                f"Application startup failed.\n\n{_preload_error[0]}",
            )
            qt_app.quit()
            return

        bootstrap_result = _bootstrap_result[0]
        if bootstrap_result is None:
            # Error already surfaced in _on_preload_done; nothing to do.
            return

        if bootstrap_result.run_post_startup_tasks is not None:
            try:
                bootstrap_result.run_post_startup_tasks()
            except Exception:
                logging.getLogger("seeker_accounting").exception(
                    "Post-startup task scheduling failed."
                )

    splash.ready_to_close.connect(_on_splash_ready)

    # Start the preloader thread
    preloader.start()

    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
