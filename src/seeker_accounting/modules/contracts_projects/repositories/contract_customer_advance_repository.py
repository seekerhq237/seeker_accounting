from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.contract_customer_advance import (
    ContractCustomerAdvance,
)


class ContractCustomerAdvanceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, advance_id: int) -> ContractCustomerAdvance | None:
        return self._session.get(ContractCustomerAdvance, advance_id)

    def get_by_advance_number(self, company_id: int, advance_number: str) -> ContractCustomerAdvance | None:
        return self._session.scalar(
            select(ContractCustomerAdvance).where(
                ContractCustomerAdvance.company_id == company_id,
                ContractCustomerAdvance.advance_number == advance_number,
            )
        )

    def list_by_contract(self, company_id: int, contract_id: int) -> list[ContractCustomerAdvance]:
        statement = (
            select(ContractCustomerAdvance)
            .where(
                ContractCustomerAdvance.company_id == company_id,
                ContractCustomerAdvance.contract_id == contract_id,
            )
            .order_by(ContractCustomerAdvance.advance_date.asc(), ContractCustomerAdvance.id.asc())
        )
        return list(self._session.scalars(statement))

    def sum_received_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractCustomerAdvance.received_amount), 0)).where(
            ContractCustomerAdvance.company_id == company_id,
            ContractCustomerAdvance.contract_id == contract_id,
            ContractCustomerAdvance.status_code != "cancelled",
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def add(self, advance: ContractCustomerAdvance) -> ContractCustomerAdvance:
        self._session.add(advance)
        return advance

    def save(self, advance: ContractCustomerAdvance) -> ContractCustomerAdvance:
        self._session.add(advance)
        return advance
