from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.inventory_location import InventoryLocation


class InventoryLocationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[InventoryLocation]:
        statement = select(InventoryLocation).where(InventoryLocation.company_id == company_id)
        if active_only:
            statement = statement.where(InventoryLocation.is_active.is_(True))
        statement = statement.order_by(InventoryLocation.code.asc(), InventoryLocation.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, location_id: int) -> InventoryLocation | None:
        statement = select(InventoryLocation).where(
            InventoryLocation.company_id == company_id,
            InventoryLocation.id == location_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, code: str) -> InventoryLocation | None:
        statement = select(InventoryLocation).where(
            InventoryLocation.company_id == company_id,
            InventoryLocation.code == code,
        )
        return self._session.scalar(statement)

    def add(self, location: InventoryLocation) -> InventoryLocation:
        self._session.add(location)
        return location

    def save(self, location: InventoryLocation) -> InventoryLocation:
        self._session.add(location)
        return location

    def code_exists(self, company_id: int, code: str, exclude_id: int | None = None) -> bool:
        predicate = (InventoryLocation.company_id == company_id) & (InventoryLocation.code == code)
        if exclude_id is not None:
            predicate = predicate & (InventoryLocation.id != exclude_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
