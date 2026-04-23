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
_SQLITE_PRAGMAS: tuple[tuple[str, str], ...] = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("temp_store", "MEMORY"),
    ("cache_size", "-65536"),
    ("mmap_size", "268435456"),
    ("foreign_keys", "ON"),
)


def _install_sqlite_pragmas(engine: Engine) -> None:
    """Apply performance/durability PRAGMAs on every new SQLite connection."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            for name, value in _SQLITE_PRAGMAS:
                cursor.execute(f"PRAGMA {name}={value}")
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

