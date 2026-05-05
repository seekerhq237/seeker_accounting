from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.inventory.models.inventory_reason_code import (
    InventoryReasonCode,
)


class InventoryReasonCodeRepository:
    """Repository for per-company inventory reason codes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self, company_id: int, active_only: bool = False
    ) -> list[InventoryReasonCode]:
        statement = select(InventoryReasonCode).where(
            InventoryReasonCode.company_id == company_id
        )
        if active_only:
            statement = statement.where(InventoryReasonCode.is_active.is_(True))
        statement = statement.order_by(
            InventoryReasonCode.code.asc(), InventoryReasonCode.id.asc()
        )
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, reason_id: int) -> InventoryReasonCode | None:
        return self._session.scalar(
            select(InventoryReasonCode).where(
                InventoryReasonCode.company_id == company_id,
                InventoryReasonCode.id == reason_id,
            )
        )

    def get_by_code(self, company_id: int, code: str) -> InventoryReasonCode | None:
        return self._session.scalar(
            select(InventoryReasonCode).where(
                InventoryReasonCode.company_id == company_id,
                InventoryReasonCode.code == code,
            )
        )

    def add(self, reason: InventoryReasonCode) -> InventoryReasonCode:
        self._session.add(reason)
        return reason

    def save(self, reason: InventoryReasonCode) -> InventoryReasonCode:
        self._session.add(reason)
        return reason

    def code_exists(
        self, company_id: int, code: str, exclude_id: int | None = None
    ) -> bool:
        predicate = (InventoryReasonCode.company_id == company_id) & (
            InventoryReasonCode.code == code
        )
        if exclude_id is not None:
            predicate = predicate & (InventoryReasonCode.id != exclude_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
