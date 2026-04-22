from __future__ import annotations

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.customers.models.customer import Customer


class CustomerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[Customer]:
        statement = select(Customer).where(Customer.company_id == company_id)
        if active_only:
            statement = statement.where(Customer.is_active.is_(True))
        statement = statement.order_by(Customer.display_name.asc(), Customer.customer_code.asc(), Customer.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, customer_id: int) -> Customer | None:
        statement = select(Customer).where(
            Customer.company_id == company_id,
            Customer.id == customer_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, customer_code: str) -> Customer | None:
        statement = select(Customer).where(
            Customer.company_id == company_id,
            Customer.customer_code == customer_code,
        )
        return self._session.scalar(statement)

    def search_by_name_or_code(
        self,
        company_id: int,
        query: str,
        active_only: bool = False,
    ) -> list[Customer]:
        search_value = f"%{query.strip().lower()}%"
        statement = select(Customer).where(
            Customer.company_id == company_id,
            or_(
                func.lower(Customer.customer_code).like(search_value),
                func.lower(Customer.display_name).like(search_value),
                func.lower(func.coalesce(Customer.legal_name, "")).like(search_value),
            ),
        )
        if active_only:
            statement = statement.where(Customer.is_active.is_(True))
        statement = statement.order_by(Customer.display_name.asc(), Customer.customer_code.asc(), Customer.id.asc())
        return list(self._session.scalars(statement))

    def add(self, customer: Customer) -> Customer:
        self._session.add(customer)
        return customer

    def save(self, customer: Customer) -> Customer:
        self._session.add(customer)
        return customer

    def code_exists(self, company_id: int, customer_code: str, exclude_customer_id: int | None = None) -> bool:
        predicate = (Customer.company_id == company_id) & (Customer.customer_code == customer_code)
        if exclude_customer_id is not None:
            predicate = predicate & (Customer.id != exclude_customer_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
