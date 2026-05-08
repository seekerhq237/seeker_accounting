from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item import Item


class ItemRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Private helpers ───────────────────────────────────────────────────────

    def _base_filter(
        self,
        company_id: int,
        query: str | None = None,
        active_only: bool = False,
        item_type_code: str | None = None,
    ):
        stmt = select(Item).where(Item.company_id == company_id)
        if active_only:
            stmt = stmt.where(Item.is_active.is_(True))
        if item_type_code is not None:
            stmt = stmt.where(Item.item_type_code == item_type_code)
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Item.item_code.ilike(pattern),
                    Item.item_name.ilike(pattern),
                )
            )
        return stmt.order_by(Item.item_code)

    # ── Public API ────────────────────────────────────────────────────────────

    def list_by_company(
        self,
        company_id: int,
        active_only: bool = False,
        item_type_code: str | None = None,
    ) -> list[Item]:
        stmt = self._base_filter(company_id, active_only=active_only, item_type_code=item_type_code)
        return list(self._session.scalars(stmt))

    def list_filtered_page(
        self,
        company_id: int,
        query: str | None = None,
        active_only: bool = False,
        item_type_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Item]:
        stmt = self._base_filter(company_id, query, active_only, item_type_code)
        stmt = stmt.offset(max(offset, 0)).limit(max(limit, 1))
        return list(self._session.scalars(stmt))

    def count_filtered(
        self,
        company_id: int,
        query: str | None = None,
        active_only: bool = False,
        item_type_code: str | None = None,
    ) -> int:
        inner = self._base_filter(company_id, query, active_only, item_type_code)
        count_stmt = select(func.count()).select_from(inner.subquery())
        return self._session.scalar(count_stmt) or 0

    def get_by_id(self, company_id: int, item_id: int) -> Item | None:
        stmt = select(Item).where(Item.company_id == company_id, Item.id == item_id)
        return self._session.scalar(stmt)

    def get_by_code(self, company_id: int, item_code: str) -> Item | None:
        stmt = select(Item).where(Item.company_id == company_id, Item.item_code == item_code)
        return self._session.scalar(stmt)

    def add(self, entity: Item) -> Item:
        self._session.add(entity)
        return entity

    def save(self, entity: Item) -> Item:
        self._session.add(entity)
        return entity
