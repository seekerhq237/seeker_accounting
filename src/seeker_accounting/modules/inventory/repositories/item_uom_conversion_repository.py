from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.item_uom_conversion import (
    ItemUomConversion,
)


class ItemUomConversionRepository:
    """Repository for per-item unit-of-measure conversion rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_item(
        self, company_id: int, item_id: int, active_only: bool = False
    ) -> list[ItemUomConversion]:
        statement = select(ItemUomConversion).where(
            ItemUomConversion.company_id == company_id,
            ItemUomConversion.item_id == item_id,
        )
        if active_only:
            statement = statement.where(ItemUomConversion.is_active.is_(True))
        statement = statement.order_by(ItemUomConversion.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(
        self, company_id: int, conversion_id: int
    ) -> ItemUomConversion | None:
        return self._session.scalar(
            select(ItemUomConversion).where(
                ItemUomConversion.company_id == company_id,
                ItemUomConversion.id == conversion_id,
            )
        )

    def get_by_item_and_uom(
        self, company_id: int, item_id: int, unit_of_measure_id: int
    ) -> ItemUomConversion | None:
        return self._session.scalar(
            select(ItemUomConversion).where(
                ItemUomConversion.company_id == company_id,
                ItemUomConversion.item_id == item_id,
                ItemUomConversion.unit_of_measure_id == unit_of_measure_id,
            )
        )

    def add(self, conversion: ItemUomConversion) -> ItemUomConversion:
        self._session.add(conversion)
        return conversion

    def save(self, conversion: ItemUomConversion) -> ItemUomConversion:
        self._session.add(conversion)
        return conversion
