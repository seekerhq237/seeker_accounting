from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.contract_change_order import ContractChangeOrder


class ContractChangeOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, change_order_id: int) -> ContractChangeOrder | None:
        return self._session.get(ContractChangeOrder, change_order_id)

    def get_by_company_and_id(self, company_id: int, change_order_id: int) -> ContractChangeOrder | None:
        return self._session.scalar(
            select(ContractChangeOrder).where(
                ContractChangeOrder.company_id == company_id,
                ContractChangeOrder.id == change_order_id,
            )
        )

    def get_by_company_and_change_order_number(
        self, company_id: int, change_order_number: str
    ) -> ContractChangeOrder | None:
        return self._session.scalar(
            select(ContractChangeOrder).where(
                ContractChangeOrder.company_id == company_id,
                ContractChangeOrder.change_order_number == change_order_number,
            )
        )

    def list_by_contract(self, contract_id: int) -> list[ContractChangeOrder]:
        return list(
            self._session.scalars(
                select(ContractChangeOrder)
                .where(ContractChangeOrder.contract_id == contract_id)
                .order_by(ContractChangeOrder.change_order_date.asc(), ContractChangeOrder.id.asc())
            )
        )

    def sum_approved_amount_delta(self, contract_id: int) -> Decimal:
        result = self._session.scalar(
            select(func.coalesce(func.sum(ContractChangeOrder.contract_amount_delta), 0)).where(
                ContractChangeOrder.contract_id == contract_id,
                ContractChangeOrder.status_code == "approved",
            )
        )
        return Decimal(str(result)) if result is not None else Decimal("0")

    def add(self, change_order: ContractChangeOrder) -> ContractChangeOrder:
        self._session.add(change_order)
        return change_order

    def save(self, change_order: ContractChangeOrder) -> ContractChangeOrder:
        self._session.add(change_order)
        return change_order
