from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.customers.models.customer_group import CustomerGroup


class CustomerGroupRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[CustomerGroup]:
        statement = select(CustomerGroup).where(CustomerGroup.company_id == company_id)
        if active_only:
            statement = statement.where(CustomerGroup.is_active.is_(True))
        statement = statement.order_by(CustomerGroup.name.asc(), CustomerGroup.code.asc(), CustomerGroup.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, group_id: int) -> CustomerGroup | None:
        statement = select(CustomerGroup).where(
            CustomerGroup.company_id == company_id,
            CustomerGroup.id == group_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, code: str) -> CustomerGroup | None:
        statement = select(CustomerGroup).where(
            CustomerGroup.company_id == company_id,
            CustomerGroup.code == code,
        )
        return self._session.scalar(statement)

    def add(self, customer_group: CustomerGroup) -> CustomerGroup:
        self._session.add(customer_group)
        return customer_group

    def save(self, customer_group: CustomerGroup) -> CustomerGroup:
        self._session.add(customer_group)
        return customer_group

    def code_exists(self, company_id: int, code: str, exclude_group_id: int | None = None) -> bool:
        predicate = (CustomerGroup.company_id == company_id) & (CustomerGroup.code == code)
        if exclude_group_id is not None:
            predicate = predicate & (CustomerGroup.id != exclude_group_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
