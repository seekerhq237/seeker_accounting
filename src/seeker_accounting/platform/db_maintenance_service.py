"""Periodic SQLite maintenance — PRAGMA optimize + passive WAL checkpoint.

Runs on a 15-minute QTimer so the query-planner statistics and WAL file
stay healthy without interrupting user-visible operations.

Design notes
------------
* Only active for SQLite; silently inert for other dialects.
* PRAGMA optimize (full, no 0x10002 flag) updates query-planner stats when
  enough new queries have accumulated since the last analysis.  The
  lightweight ``0x10002`` variant that runs on every new connection handles
  the common case; the full variant here ensures stats are refreshed even
  when the connection pool reuses the same physical connection for many hours.
* ``PRAGMA wal_checkpoint(PASSIVE)`` flushes WAL frames that have already been
  read by all open readers.  It never blocks and is safe to run at any time.
  Combined with ``wal_autocheckpoint=2000`` in the engine pragmas, this keeps
  the WAL file compact in steady state.
* The service owns its own QTimer and is parented to the main window, so it
  is cleaned up automatically when the shell closes.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer
from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

_INTERVAL_MS = 15 * 60 * 1000  # 15 minutes


class DatabaseMaintenanceService(QObject):
    """Periodic SQLite PRAGMA optimize + passive WAL checkpoint.

    Attach to a parent QObject (e.g. the main window) so the timer is
    automatically stopped and deleted when the parent is destroyed.

    For non-SQLite engines the constructor returns immediately without
    starting any timer.
    """

    def __init__(self, engine: Engine, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine

        if engine.dialect.name != "sqlite":
            # No SQLite-specific maintenance needed for other dialects.
            return

        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVAL_MS)
        self._timer.timeout.connect(self._run_maintenance)
        self._timer.start()
        logger.debug(
            "DatabaseMaintenanceService started (interval=%d s).",
            _INTERVAL_MS // 1000,
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _run_maintenance(self) -> None:
        """Run PRAGMA optimize and a passive WAL checkpoint."""
        try:
            with self._engine.connect() as conn:
                # Full optimize: refresh query-planner stats accumulated since
                # the last analysis, across all tables that have seen enough
                # writes to benefit.
                conn.execute(text("PRAGMA optimize"))
                # Passive checkpoint: copy WAL frames to the main DB file as
                # far as readers allow, without blocking anyone.
                conn.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
            logger.debug("Periodic DB maintenance completed.")
        except Exception:
            logger.warning("Periodic DB maintenance failed.", exc_info=True)
