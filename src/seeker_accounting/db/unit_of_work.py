from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TypeAlias

from sqlalchemy.orm import Session, sessionmaker

SessionFactory: TypeAlias = sessionmaker[Session]


@dataclass(slots=True)
class SqlAlchemyUnitOfWork:
    session_factory: SessionFactory
    session: Session | None = field(default=None, init=False)

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self.session_factory()
        return self

    def __exit__(self, exc_type: object, exc: object, exc_tb: object) -> None:
        if self.session is None:
            return
        if exc is not None:
            self.session.rollback()
        self.session.close()
        self.session = None

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("Unit of work has no active session.")
        self.session.commit()

    def rollback(self) -> None:
        if self.session is None:
            return
        self.session.rollback()


UnitOfWorkFactory: TypeAlias = Callable[[], SqlAlchemyUnitOfWork]


def create_unit_of_work_factory(session_factory: SessionFactory) -> UnitOfWorkFactory:
    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory

