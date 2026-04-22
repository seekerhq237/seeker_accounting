"""Session idle watcher — application-level inactivity monitor.

Installs a global event filter on QApplication to detect user activity
(keyboard, mouse, wheel). After the configured idle period, a countdown
warning is displayed. If the user resumes activity during the countdown,
the warning is dismissed and the idle timer resets. Otherwise, the
``idle_logout_requested`` signal fires for the bootstrap layer to
execute a forced logout.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from seeker_accounting.platform.session.idle_timeout_warning_dialog import IdleTimeoutWarningDialog

logger = logging.getLogger(__name__)

# Event types that count as user activity.
_ACTIVITY_EVENTS = frozenset({
    QEvent.Type.KeyPress,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.MouseMove,
    QEvent.Type.Wheel,
})

_WARNING_DURATION_SEC = 30


class SessionIdleWatcherService(QObject):
    """Cross-cutting service that monitors inactivity and triggers logout."""

    idle_logout_requested = Signal()

    def __init__(self, qt_app: QApplication, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = qt_app
        self._timeout_minutes: int = 2  # default; refreshed from company prefs
        self._enabled = False
        self._warning_dialog: IdleTimeoutWarningDialog | None = None

        # Idle timer — fires once after the configured idle period.
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._show_warning)

        # Countdown timer — ticks every second during the warning phase.
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_countdown)
        self._countdown_remaining = 0

    # ── Public API ────────────────────────────────────────────────────

    def start(self, timeout_minutes: int) -> None:
        """Activate idle monitoring with the given timeout."""
        self._timeout_minutes = max(1, timeout_minutes)
        self._enabled = True
        self._app.installEventFilter(self)
        self._restart_idle_timer()
        logger.info("Idle watcher started: %d min timeout, %d sec warning.",
                     self._timeout_minutes, _WARNING_DURATION_SEC)

    def stop(self) -> None:
        """Deactivate idle monitoring (e.g. on logout)."""
        self._enabled = False
        self._idle_timer.stop()
        self._countdown_timer.stop()
        self._dismiss_warning()
        self._app.removeEventFilter(self)
        logger.info("Idle watcher stopped.")

    def update_timeout(self, timeout_minutes: int) -> None:
        """Update the idle timeout without restarting the full lifecycle."""
        if not self._enabled:
            return
        self._timeout_minutes = max(1, timeout_minutes)
        self._restart_idle_timer()

    # ── Qt event filter ───────────────────────────────────────────────

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if self._enabled and event.type() in _ACTIVITY_EVENTS:
            self._on_user_activity()
        return False  # never consume events

    # ── Internal ──────────────────────────────────────────────────────

    def _on_user_activity(self) -> None:
        """Reset idle tracking. If the warning countdown is active, ignore
        generic activity — the user must click 'Stay Logged In' explicitly."""
        if self._countdown_timer.isActive():
            return
        self._restart_idle_timer()

    def _restart_idle_timer(self) -> None:
        self._idle_timer.start(self._timeout_minutes * 60 * 1000)

    def _show_warning(self) -> None:
        """Display the countdown warning dialog."""
        # If the user is actively working in a modal dialog (create/edit form,
        # wizard, etc.), defer the timeout — don't interrupt their work.
        if self._app.activeModalWidget() is not None:
            logger.debug("Idle timeout deferred — modal dialog is active.")
            self._restart_idle_timer()
            return

        from seeker_accounting.platform.session.idle_timeout_warning_dialog import (
            IdleTimeoutWarningDialog,
        )

        self._countdown_remaining = _WARNING_DURATION_SEC

        active_window = self._app.activeWindow()
        self._warning_dialog = IdleTimeoutWarningDialog(
            seconds_remaining=self._countdown_remaining,
            parent=active_window,
        )
        self._warning_dialog.stay_logged_in_requested.connect(self._on_stay_logged_in)
        self._warning_dialog.show()
        self._warning_dialog.raise_()
        self._countdown_timer.start()
        logger.info("Idle warning shown — %d seconds to auto-logout.", self._countdown_remaining)

    def _tick_countdown(self) -> None:
        self._countdown_remaining -= 1
        if self._warning_dialog is not None:
            self._warning_dialog.update_countdown(self._countdown_remaining)
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            self._dismiss_warning()
            logger.info("Idle timeout reached — requesting logout.")
            self.idle_logout_requested.emit()

    def _on_stay_logged_in(self) -> None:
        """User clicked 'Stay Logged In'."""
        self._countdown_timer.stop()
        self._dismiss_warning()
        self._restart_idle_timer()

    def _dismiss_warning(self) -> None:
        if self._warning_dialog is not None:
            self._warning_dialog.close()
            self._warning_dialog.deleteLater()
            self._warning_dialog = None
