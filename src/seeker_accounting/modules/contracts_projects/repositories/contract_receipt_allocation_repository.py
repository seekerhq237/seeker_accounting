from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.contract_receipt_allocation import (
    ContractReceiptAllocation,
)


class ContractReceiptAllocationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_contract(self, company_id: int, contract_id: int) -> list[ContractReceiptAllocation]:
        statement = (
            select(ContractReceiptAllocation)
            .where(
                ContractReceiptAllocation.company_id == company_id,
                ContractReceiptAllocation.contract_id == contract_id,
            )
            .order_by(ContractReceiptAllocation.allocation_date.asc(), ContractReceiptAllocation.id.asc())
        )
        return list(self._session.scalars(statement))

    def sum_collected_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractReceiptAllocation.total_allocated_amount), 0)).where(
            ContractReceiptAllocation.company_id == company_id,
            ContractReceiptAllocation.contract_id == contract_id,
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def add(self, allocation: ContractReceiptAllocation) -> ContractReceiptAllocation:
        self._session.add(allocation)
        return allocation

    def save(self, allocation: ContractReceiptAllocation) -> ContractReceiptAllocation:
        self._session.add(allocation)
        return allocation
