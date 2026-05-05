from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_account_override import (
    ItemAccountOverride,
)


class ItemAccountOverrideRepository:
    """Repository for per-(item, location) GL account overrides."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_item(
        self, company_id: int, item_id: int
    ) -> list[ItemAccountOverride]:
        statement = (
            select(ItemAccountOverride)
            .where(
                ItemAccountOverride.company_id == company_id,
                ItemAccountOverride.item_id == item_id,
            )
            .order_by(
                ItemAccountOverride.location_id.is_(None).desc(),
                ItemAccountOverride.location_id.asc(),
            )
        )
        return list(self._session.scalars(statement))

    def get_by_id(
        self, company_id: int, override_id: int
    ) -> ItemAccountOverride | None:
        return self._session.scalar(
            select(ItemAccountOverride).where(
                ItemAccountOverride.company_id == company_id,
                ItemAccountOverride.id == override_id,
            )
        )

    def get_for_item_and_location(
        self,
        company_id: int,
        item_id: int,
        location_id: int | None,
    ) -> ItemAccountOverride | None:
        statement = select(ItemAccountOverride).where(
            ItemAccountOverride.company_id == company_id,
            ItemAccountOverride.item_id == item_id,
        )
        if location_id is None:
            statement = statement.where(ItemAccountOverride.location_id.is_(None))
        else:
            statement = statement.where(
                ItemAccountOverride.location_id == location_id
            )
        return self._session.scalar(statement)

    def add(self, override: ItemAccountOverride) -> ItemAccountOverride:
        self._session.add(override)
        return override

    def save(self, override: ItemAccountOverride) -> ItemAccountOverride:
        self._session.add(override)
        return override

    def delete(self, override: ItemAccountOverride) -> None:
        self._session.delete(override)
