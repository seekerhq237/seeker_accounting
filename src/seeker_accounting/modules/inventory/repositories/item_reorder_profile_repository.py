"""Repository for ItemReorderProfile (P6 / Slice 7.2)."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_reorder_profile import ItemReorderProfile


class ItemReorderProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, profile_id: int) -> ItemReorderProfile | None:
        return self._session.get(ItemReorderProfile, profile_id)

    def get_for_item_location(
        self, company_id: int, item_id: int, location_id: int | None
    ) -> ItemReorderProfile | None:
        stmt = select(ItemReorderProfile).where(
            ItemReorderProfile.company_id == company_id,
            ItemReorderProfile.item_id == item_id,
            ItemReorderProfile.location_id == location_id,
        )
        return self._session.scalars(stmt).first()

    def list_by_company(self, company_id: int) -> Sequence[ItemReorderProfile]:
        stmt = (
            select(ItemReorderProfile)
            .where(ItemReorderProfile.company_id == company_id)
            .order_by(ItemReorderProfile.item_id)
        )
        return self._session.scalars(stmt).all()

    def add(self, profile: ItemReorderProfile) -> None:
        self._session.add(profile)

    def delete(self, profile: ItemReorderProfile) -> None:
        self._session.delete(profile)
