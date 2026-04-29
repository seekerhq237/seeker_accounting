"""Repository for ``TaxPayment``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.tax_payment import TaxPayment


class TaxPaymentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, company_id: int, payment_id: int) -> TaxPayment | None:
        stmt = select(TaxPayment).where(
            TaxPayment.id == payment_id,
            TaxPayment.company_id == company_id,
        )
        return self._session.scalar(stmt)

    def list_by_return(self, company_id: int, return_id: int) -> list[TaxPayment]:
        stmt = (
            select(TaxPayment)
            .where(
                TaxPayment.company_id == company_id,
                TaxPayment.tax_return_id == return_id,
            )
            .order_by(TaxPayment.payment_date.asc(), TaxPayment.id.asc())
        )
        return list(self._session.scalars(stmt))

    def list_by_company(self, company_id: int) -> list[TaxPayment]:
        stmt = (
            select(TaxPayment)
            .where(TaxPayment.company_id == company_id)
            .order_by(TaxPayment.payment_date.desc(), TaxPayment.id.desc())
        )
        return list(self._session.scalars(stmt))

    def add(self, payment: TaxPayment) -> TaxPayment:
        self._session.add(payment)
        return payment

    def save(self, payment: TaxPayment) -> TaxPayment:
        self._session.add(payment)
        return payment
