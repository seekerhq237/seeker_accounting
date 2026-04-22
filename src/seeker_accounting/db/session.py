from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    from seeker_accounting.db.model_registry import load_model_registry

    load_model_registry()
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
