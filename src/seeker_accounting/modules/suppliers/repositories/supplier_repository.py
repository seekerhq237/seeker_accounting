from __future__ import annotations

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.suppliers.models.supplier import Supplier


class SupplierRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[Supplier]:
        statement = select(Supplier).where(Supplier.company_id == company_id)
        if active_only:
            statement = statement.where(Supplier.is_active.is_(True))
        statement = statement.order_by(Supplier.display_name.asc(), Supplier.supplier_code.asc(), Supplier.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, supplier_id: int) -> Supplier | None:
        statement = select(Supplier).where(
            Supplier.company_id == company_id,
            Supplier.id == supplier_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, supplier_code: str) -> Supplier | None:
        statement = select(Supplier).where(
            Supplier.company_id == company_id,
            Supplier.supplier_code == supplier_code,
        )
        return self._session.scalar(statement)

    def search_by_name_or_code(
        self,
        company_id: int,
        query: str,
        active_only: bool = False,
    ) -> list[Supplier]:
        search_value = f"%{query.strip().lower()}%"
        statement = select(Supplier).where(
            Supplier.company_id == company_id,
            or_(
                func.lower(Supplier.supplier_code).like(search_value),
                func.lower(Supplier.display_name).like(search_value),
                func.lower(func.coalesce(Supplier.legal_name, "")).like(search_value),
            ),
        )
        if active_only:
            statement = statement.where(Supplier.is_active.is_(True))
        statement = statement.order_by(Supplier.display_name.asc(), Supplier.supplier_code.asc(), Supplier.id.asc())
        return list(self._session.scalars(statement))

    def add(self, supplier: Supplier) -> Supplier:
        self._session.add(supplier)
        return supplier

    def save(self, supplier: Supplier) -> Supplier:
        self._session.add(supplier)
        return supplier

    def code_exists(self, company_id: int, supplier_code: str, exclude_supplier_id: int | None = None) -> bool:
        predicate = (Supplier.company_id == company_id) & (Supplier.supplier_code == supplier_code)
        if exclude_supplier_id is not None:
            predicate = predicate & (Supplier.id != exclude_supplier_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
