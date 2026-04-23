from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.treasury.models.treasury_transaction import TreasuryTransaction


class TreasuryTransactionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
        transaction_type_code: str | None = None,
    ) -> list[TreasuryTransaction]:
        statement = select(TreasuryTransaction).where(
            TreasuryTransaction.company_id == company_id
        )
        if status_code is not None:
            statement = statement.where(TreasuryTransaction.status_code == status_code)
        if transaction_type_code is not None:
            statement = statement.where(TreasuryTransaction.transaction_type_code == transaction_type_code)
        statement = statement.options(
            selectinload(TreasuryTransaction.financial_account),
            selectinload(TreasuryTransaction.currency),
        )
        statement = statement.order_by(TreasuryTransaction.transaction_date.desc(), TreasuryTransaction.id.desc())
        return list(self._session.scalars(statement))

    # ------------------------------------------------------------------
    # Paginated + searchable listing (server-side)
    # ------------------------------------------------------------------

    def _build_filter_conditions(
        self,
        company_id: int,
        status_code: str | None,
        transaction_type_code: str | None,
        query: str | None,
    ) -> list:
        conditions: list = [TreasuryTransaction.company_id == company_id]
        if status_code is not None:
            conditions.append(TreasuryTransaction.status_code == status_code)
        if transaction_type_code is not None:
            conditions.append(TreasuryTransaction.transaction_type_code == transaction_type_code)
        if query:
            like = f"%{query.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(TreasuryTransaction.transaction_number).like(like),
                    func.lower(TreasuryTransaction.reference_number).like(like),
                    func.lower(TreasuryTransaction.description).like(like),
                )
            )
        return conditions

    def count_filtered(
        self,
        company_id: int,
        status_code: str | None = None,
        transaction_type_code: str | None = None,
        query: str | None = None,
    ) -> int:
        stmt = select(func.count(TreasuryTransaction.id)).where(
            *self._build_filter_conditions(company_id, status_code, transaction_type_code, query)
        )
        return int(self._session.scalar(stmt) or 0)

    def list_filtered_page(
        self,
        company_id: int,
        status_code: str | None = None,
        transaction_type_code: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TreasuryTransaction]:
        stmt = (
            select(TreasuryTransaction)
            .where(
                *self._build_filter_conditions(company_id, status_code, transaction_type_code, query)
            )
            .options(
                selectinload(TreasuryTransaction.financial_account),
                selectinload(TreasuryTransaction.currency),
            )
            .order_by(
                TreasuryTransaction.transaction_date.desc(),
                TreasuryTransaction.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, transaction_id: int) -> TreasuryTransaction | None:
        statement = select(TreasuryTransaction).where(
            TreasuryTransaction.company_id == company_id,
            TreasuryTransaction.id == transaction_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, transaction_id: int) -> TreasuryTransaction | None:
        statement = select(TreasuryTransaction).where(
            TreasuryTransaction.company_id == company_id,
            TreasuryTransaction.id == transaction_id,
        ).options(
            selectinload(TreasuryTransaction.financial_account),
            selectinload(TreasuryTransaction.currency),
            selectinload(TreasuryTransaction.lines),
        )
        return self._session.scalar(statement)

    def add(self, entity: TreasuryTransaction) -> TreasuryTransaction:
        self._session.add(entity)
        return entity

    def save(self, entity: TreasuryTransaction) -> TreasuryTransaction:
        self._session.add(entity)
        return entity
