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
    _preload_result = [None]  # mutable container for closure
    _preload_error = [None]   # mutable container for closure

    def _on_preload_done(result: object) -> None:
        _preload_result[0] = result
        splash.mark_preload_done()

    def _on_preload_failed(error_msg: str) -> None:
        _preload_error[0] = error_msg
        splash.mark_preload_failed(error_msg)

    preloader.progress.connect(splash.set_status)
    preloader.finished_ok.connect(_on_preload_done)
    preloader.failed.connect(_on_preload_failed)

    # ── When splash animation + preload both complete, bootstrap ─────
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

        result = _preload_result[0]
        if result is None:
            splash.close()
            QMessageBox.critical(None, APP_NAME, "Application startup failed.\n\nNo preload result.")
            qt_app.quit()
            return

        try:
            from seeker_accounting.app.bootstrap.application import bootstrap_application
            from seeker_accounting import __version__

            splash.set_version_text(f"Version {__version__}")

            bootstrap_application(
                qt_app=qt_app,
                settings=result.settings,
                app_context=result.app_context,
                session_context=result.session_context,
                initial_landing=splash,
            )
        except Exception as exc:
            splash.close()
            logging.getLogger("seeker_accounting").exception("Application startup failed.")
            QMessageBox.critical(None, APP_NAME, f"Application startup failed.\n\n{exc}")
            qt_app.quit()
            return

    splash.ready_to_close.connect(_on_splash_ready)

    # Start the preloader thread
    preloader.start()

    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
