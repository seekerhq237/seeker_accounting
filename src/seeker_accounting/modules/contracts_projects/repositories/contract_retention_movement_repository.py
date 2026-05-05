from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.contract_retention_movement import (
    ContractRetentionMovement,
)

_RELEASE_TYPES = {"partial_release", "final_release", "write_off"}


class ContractRetentionMovementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_contract(self, company_id: int, contract_id: int) -> list[ContractRetentionMovement]:
        statement = (
            select(ContractRetentionMovement)
            .where(
                ContractRetentionMovement.company_id == company_id,
                ContractRetentionMovement.contract_id == contract_id,
            )
            .order_by(ContractRetentionMovement.movement_date.asc(), ContractRetentionMovement.id.asc())
        )
        return list(self._session.scalars(statement))

    def open_retention_balance(self, company_id: int, contract_id: int) -> Decimal:
        balance = Decimal("0.00")
        for movement in self.list_by_contract(company_id, contract_id):
            if movement.status_code == "cancelled":
                continue
            amount = Decimal(str(movement.amount or 0))
            if movement.movement_type_code in _RELEASE_TYPES:
                balance -= amount
            else:
                balance += amount
        return balance.quantize(Decimal("0.00"))

    def add(self, movement: ContractRetentionMovement) -> ContractRetentionMovement:
        self._session.add(movement)
        return movement

    def save(self, movement: ContractRetentionMovement) -> ContractRetentionMovement:
        self._session.add(movement)
        return movement
