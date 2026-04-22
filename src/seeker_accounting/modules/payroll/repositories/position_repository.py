from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.payroll.models.position import Position


class PositionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[Position]:
        stmt = (
            select(Position)
            .where(Position.company_id == company_id)
            .order_by(Position.code)
        )
        if active_only:
            stmt = stmt.where(Position.is_active == True)  # noqa: E712
        return list(self._session.scalars(stmt).all())

    def get_by_id(self, company_id: int, position_id: int) -> Position | None:
        stmt = (
            select(Position)
            .where(Position.id == position_id)
            .where(Position.company_id == company_id)
        )
        return self._session.scalar(stmt)

    def get_by_code(self, company_id: int, code: str) -> Position | None:
        stmt = (
            select(Position)
            .where(Position.company_id == company_id)
            .where(Position.code == code)
        )
        return self._session.scalar(stmt)

    def save(self, position: Position) -> Position:
        self._session.add(position)
        return position
