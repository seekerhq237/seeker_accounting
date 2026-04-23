from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.purchases.models.supplier_payment import SupplierPayment
from seeker_accounting.modules.purchases.models.supplier_payment_allocation import SupplierPaymentAllocation
from seeker_accounting.modules.suppliers.models.supplier import Supplier


class SupplierPaymentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, status_code: str | None = None) -> list[SupplierPayment]:
        statement = select(SupplierPayment).where(SupplierPayment.company_id == company_id)
        if status_code is not None:
            statement = statement.where(SupplierPayment.status_code == status_code)
        statement = statement.options(selectinload(SupplierPayment.supplier), selectinload(SupplierPayment.financial_account))
        statement = statement.order_by(
            SupplierPayment.payment_date.desc(),
            SupplierPayment.payment_number.desc(),
            SupplierPayment.id.desc(),
        )
        return list(self._session.scalars(statement))

    # ------------------------------------------------------------------
    # Paginated + searchable listing
    # ------------------------------------------------------------------

    def _build_filter_conditions(
        self,
        company_id: int,
        status_code: str | None,
        query: str | None,
    ) -> list:
        conditions: list = [SupplierPayment.company_id == company_id]
        if status_code is not None:
            conditions.append(SupplierPayment.status_code == status_code)
        if query:
            like = f"%{query.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(SupplierPayment.payment_number).like(like),
                    func.lower(SupplierPayment.reference_number).like(like),
                    func.lower(Supplier.display_name).like(like),
                    func.lower(Supplier.supplier_code).like(like),
                )
            )
        return conditions

    def count_filtered(
        self,
        company_id: int,
        status_code: str | None = None,
        query: str | None = None,
    ) -> int:
        stmt = (
            select(func.count(SupplierPayment.id))
            .join(Supplier, Supplier.id == SupplierPayment.supplier_id)
            .where(*self._build_filter_conditions(company_id, status_code, query))
        )
        return int(self._session.scalar(stmt) or 0)

    def list_filtered_page(
        self,
        company_id: int,
        status_code: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SupplierPayment]:
        stmt = (
            select(SupplierPayment)
            .join(Supplier, Supplier.id == SupplierPayment.supplier_id)
            .where(*self._build_filter_conditions(company_id, status_code, query))
            .options(
                selectinload(SupplierPayment.supplier),
                selectinload(SupplierPayment.financial_account),
            )
            .order_by(
                SupplierPayment.payment_date.desc(),
                SupplierPayment.payment_number.desc(),
                SupplierPayment.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, payment_id: int) -> SupplierPayment | None:
        statement = select(SupplierPayment).where(
            SupplierPayment.company_id == company_id,
            SupplierPayment.id == payment_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, payment_id: int) -> SupplierPayment | None:
        statement = select(SupplierPayment).where(
            SupplierPayment.company_id == company_id,
            SupplierPayment.id == payment_id,
        )
        statement = statement.options(
            selectinload(SupplierPayment.supplier),
            selectinload(SupplierPayment.currency),
            selectinload(SupplierPayment.financial_account),
            selectinload(SupplierPayment.posted_journal_entry),
            selectinload(SupplierPayment.posted_by_user),
            selectinload(SupplierPayment.allocations)
            .selectinload(SupplierPaymentAllocation.purchase_bill),
        )
        return self._session.scalar(statement)

    def get_by_number(self, company_id: int, payment_number: str) -> SupplierPayment | None:
        statement = select(SupplierPayment).where(
            SupplierPayment.company_id == company_id,
            SupplierPayment.payment_number == payment_number,
        )
        return self._session.scalar(statement)

    def add(self, payment: SupplierPayment) -> SupplierPayment:
        self._session.add(payment)
        return payment

    def save(self, payment: SupplierPayment) -> SupplierPayment:
        self._session.add(payment)
        return payment
