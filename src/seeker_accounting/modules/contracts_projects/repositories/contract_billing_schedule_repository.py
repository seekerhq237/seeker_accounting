from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.contracts_projects.models.contract_billing_schedule_item import (
    ContractBillingScheduleItem,
)


class ContractBillingScheduleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, schedule_item_id: int) -> ContractBillingScheduleItem | None:
        return self._session.get(ContractBillingScheduleItem, schedule_item_id)

    def list_by_contract(self, company_id: int, contract_id: int) -> list[ContractBillingScheduleItem]:
        statement = (
            select(ContractBillingScheduleItem)
            .where(
                ContractBillingScheduleItem.company_id == company_id,
                ContractBillingScheduleItem.contract_id == contract_id,
            )
            .order_by(
                ContractBillingScheduleItem.line_number.asc(),
                ContractBillingScheduleItem.id.asc(),
            )
        )
        return list(self._session.scalars(statement))

    def replace_items(
        self,
        company_id: int,
        contract_id: int,
        items: list[ContractBillingScheduleItem],
    ) -> list[ContractBillingScheduleItem]:
        existing_statement = select(ContractBillingScheduleItem).where(
            ContractBillingScheduleItem.company_id == company_id,
            ContractBillingScheduleItem.contract_id == contract_id,
        )
        for existing_item in self._session.scalars(existing_statement):
            self._session.delete(existing_item)
        self._session.flush()
        for item in items:
            item.company_id = company_id
            item.contract_id = contract_id
            self._session.add(item)
        return items

    def sum_active_amount(self, company_id: int, contract_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ContractBillingScheduleItem.scheduled_amount), 0)).where(
            ContractBillingScheduleItem.company_id == company_id,
            ContractBillingScheduleItem.contract_id == contract_id,
            ContractBillingScheduleItem.status_code != "cancelled",
        )
        return Decimal(str(self._session.scalar(statement) or 0)).quantize(Decimal("0.00"))

    def add(self, item: ContractBillingScheduleItem) -> ContractBillingScheduleItem:
        self._session.add(item)
        return item

    def save(self, item: ContractBillingScheduleItem) -> ContractBillingScheduleItem:
        self._session.add(item)
        return item
