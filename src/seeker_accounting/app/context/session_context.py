from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory


@dataclass(slots=True, frozen=True)
class SessionContext:
    engine: Engine
    session_factory: sessionmaker[Session]
    unit_of_work_factory: UnitOfWorkFactory

