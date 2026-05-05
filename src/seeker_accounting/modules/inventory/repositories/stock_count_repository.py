from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.inventory.models.stock_count_line import StockCountLine
from seeker_accounting.modules.inventory.models.stock_count_plan import StockCountPlan
from seeker_accounting.modules.inventory.models.stock_count_session import StockCountSession


class StockCountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_plans(self, company_id: int) -> list[StockCountPlan]:
        stmt = (
            select(StockCountPlan)
            .where(StockCountPlan.company_id == company_id)
            .options(selectinload(StockCountPlan.locations))
            .order_by(StockCountPlan.plan_date.desc(), StockCountPlan.id.desc())
        )
        return list(self._session.scalars(stmt))

    def list_sessions(self, company_id: int, plan_id: int | None = None) -> list[StockCountSession]:
        stmt = (
            select(StockCountSession)
            .where(StockCountSession.company_id == company_id)
            .options(selectinload(StockCountSession.lines))
            .order_by(StockCountSession.session_date.desc(), StockCountSession.id.desc())
        )
        if plan_id is not None:
            stmt = stmt.where(StockCountSession.plan_id == plan_id)
        return list(self._session.scalars(stmt))

    def get_plan(self, company_id: int, plan_id: int) -> StockCountPlan | None:
        stmt = (
            select(StockCountPlan)
            .where(StockCountPlan.company_id == company_id, StockCountPlan.id == plan_id)
            .options(selectinload(StockCountPlan.locations), selectinload(StockCountPlan.sessions))
        )
        return self._session.scalar(stmt)

    def get_session(self, company_id: int, session_id: int) -> StockCountSession | None:
        stmt = (
            select(StockCountSession)
            .where(StockCountSession.company_id == company_id, StockCountSession.id == session_id)
            .options(selectinload(StockCountSession.lines))
        )
        return self._session.scalar(stmt)

    def get_line(self, line_id: int) -> StockCountLine | None:
        return self._session.get(StockCountLine, line_id)

    def add_plan(self, entity: StockCountPlan) -> StockCountPlan:
        self._session.add(entity)
        return entity

    def add_session(self, entity: StockCountSession) -> StockCountSession:
        self._session.add(entity)
        return entity

    def save_plan(self, entity: StockCountPlan) -> StockCountPlan:
        self._session.add(entity)
        return entity

    def save_session(self, entity: StockCountSession) -> StockCountSession:
        self._session.add(entity)
        return entity

    def save_line(self, entity: StockCountLine) -> StockCountLine:
        self._session.add(entity)
        return entity