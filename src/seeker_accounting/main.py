from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from seeker_accounting.config.constants import APP_NAME, ORGANIZATION_NAME


def main() -> int:
    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setApplicationName(APP_NAME)
    qt_app.setOrganizationName(ORGANIZATION_NAME)
    qt_app.setStyle("Fusion")
    qt_app.setQuitOnLastWindowClosed(True)

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
