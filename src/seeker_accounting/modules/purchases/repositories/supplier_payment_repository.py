from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.purchases.models.supplier_payment import SupplierPayment
from seeker_accounting.modules.purchases.models.supplier_payment_allocation import SupplierPaymentAllocation


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
