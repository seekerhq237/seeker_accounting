from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.payment_term import PaymentTerm


class PaymentTermRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(self, company_id: int, active_only: bool = False) -> list[PaymentTerm]:
        statement = select(PaymentTerm).where(PaymentTerm.company_id == company_id)
        if active_only:
            statement = statement.where(PaymentTerm.is_active.is_(True))
        statement = statement.order_by(PaymentTerm.name.asc(), PaymentTerm.code.asc(), PaymentTerm.id.asc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, payment_term_id: int) -> PaymentTerm | None:
        statement = select(PaymentTerm).where(
            PaymentTerm.company_id == company_id,
            PaymentTerm.id == payment_term_id,
        )
        return self._session.scalar(statement)

    def get_by_code(self, company_id: int, code: str) -> PaymentTerm | None:
        statement = select(PaymentTerm).where(
            PaymentTerm.company_id == company_id,
            PaymentTerm.code == code,
        )
        return self._session.scalar(statement)

    def get_by_name(self, company_id: int, name: str) -> PaymentTerm | None:
        statement = select(PaymentTerm).where(
            PaymentTerm.company_id == company_id,
            PaymentTerm.name == name,
        )
        return self._session.scalar(statement)

    def add(self, payment_term: PaymentTerm) -> PaymentTerm:
        self._session.add(payment_term)
        return payment_term

    def save(self, payment_term: PaymentTerm) -> PaymentTerm:
        self._session.add(payment_term)
        return payment_term

    def code_exists(self, company_id: int, code: str, exclude_payment_term_id: int | None = None) -> bool:
        predicate = (PaymentTerm.company_id == company_id) & (PaymentTerm.code == code)
        if exclude_payment_term_id is not None:
            predicate = predicate & (PaymentTerm.id != exclude_payment_term_id)
        return bool(self._session.scalar(select(exists().where(predicate))))

    def name_exists(self, company_id: int, name: str, exclude_payment_term_id: int | None = None) -> bool:
        predicate = (PaymentTerm.company_id == company_id) & (PaymentTerm.name == name)
        if exclude_payment_term_id is not None:
            predicate = predicate & (PaymentTerm.id != exclude_payment_term_id)
        return bool(self._session.scalar(select(exists().where(predicate))))
