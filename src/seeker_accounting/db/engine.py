from __future__ import annotations

from sqlalchemy import Engine, create_engine, event

from seeker_accounting.config.settings import AppSettings


# Tuning rationale (SQLite):
# - WAL: readers don't block writers; much better perceived responsiveness.
# - synchronous=NORMAL: safe under WAL, far fewer fsyncs than FULL.
# - temp_store=MEMORY: intermediate results stay in RAM.
# - cache_size=-65536: ~64 MiB page cache.
# - mmap_size: let SQLite memory-map the DB for faster reads on larger files.
# - foreign_keys=ON: enforce FK constraints (off by default in SQLite).
# - busy_timeout=5000: wait up to 5 s for a locked page (WAL checkpoint / writer
#   contention) instead of returning SQLITE_BUSY immediately and crashing callers.
# - wal_autocheckpoint=2000: delay the automatic WAL-file checkpoint until 2 000
#   pages (≈8 MiB at 4 KiB pages) have accumulated.  The default of 1 000 pages
#   triggers too frequently during bulk imports or payroll runs and adds visible
#   pauses.  DatabaseMaintenanceService still issues a PASSIVE checkpoint every
#   15 minutes so the WAL file stays compact in steady state.
_SQLITE_PRAGMAS: tuple[tuple[str, str], ...] = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("temp_store", "MEMORY"),
    ("cache_size", "-65536"),
    ("mmap_size", "268435456"),
    ("foreign_keys", "ON"),
    ("busy_timeout", "5000"),
    ("wal_autocheckpoint", "2000"),
)


def _install_sqlite_pragmas(engine: Engine) -> None:
    """Apply performance/durability PRAGMAs on every new SQLite connection."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            for name, value in _SQLITE_PRAGMAS:
                cursor.execute(f"PRAGMA {name}={value}")
            # Ask SQLite to refresh query-planner statistics if enough new
            # queries have accumulated since the last analysis.  The 0x10002
            # flag makes this a lightweight no-op when stats are already fresh.
            cursor.execute("PRAGMA optimize=0x10002")
        finally:
            cursor.close()


def create_database_engine(settings: AppSettings) -> Engine:
    connect_args: dict[str, object] = {}
    is_sqlite = settings.database_url.startswith("sqlite")
    if is_sqlite:
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
        # Cache compiled SQL statements; reduces per-query Python overhead
        # across the many repository query shapes in this app.
        query_cache_size=1200,
    )

    if is_sqlite:
        _install_sqlite_pragmas(engine)

    return engine

