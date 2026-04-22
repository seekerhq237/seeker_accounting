from __future__ import annotations

from sqlalchemy import Engine, create_engine

from seeker_accounting.config.settings import AppSettings


def create_database_engine(settings: AppSettings) -> Engine:
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )

