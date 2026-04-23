from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.treasury.models.treasury_transfer import TreasuryTransfer


class TreasuryTransferRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[TreasuryTransfer]:
        statement = select(TreasuryTransfer).where(
            TreasuryTransfer.company_id == company_id
        )
        if status_code is not None:
            statement = statement.where(TreasuryTransfer.status_code == status_code)
        statement = statement.options(
            selectinload(TreasuryTransfer.from_financial_account),
            selectinload(TreasuryTransfer.to_financial_account),
            selectinload(TreasuryTransfer.currency),
        )
        statement = statement.order_by(TreasuryTransfer.transfer_date.desc(), TreasuryTransfer.id.desc())
        return list(self._session.scalars(statement))

    def _build_filter_conditions(
        self,
        company_id: int,
        status_code: str | None,
        query: str | None,
    ):
        conditions = [TreasuryTransfer.company_id == company_id]
        if status_code is not None:
            conditions.append(TreasuryTransfer.status_code == status_code)
        normalized = (query or "").strip().lower()
        if normalized:
            pattern = f"%{normalized}%"
            conditions.append(
                or_(
                    func.lower(func.coalesce(TreasuryTransfer.transfer_number, "")).like(pattern),
                    func.lower(func.coalesce(TreasuryTransfer.description, "")).like(pattern),
                    func.lower(func.coalesce(TreasuryTransfer.reference_number, "")).like(pattern),
                )
            )
        return conditions

    def count_filtered(
        self,
        company_id: int,
        status_code: str | None = None,
        query: str | None = None,
    ) -> int:
        conditions = self._build_filter_conditions(company_id, status_code, query)
        stmt = select(func.count(TreasuryTransfer.id)).where(*conditions)
        return int(self._session.scalar(stmt) or 0)

    def list_filtered_page(
        self,
        company_id: int,
        status_code: str | None = None,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TreasuryTransfer]:
        conditions = self._build_filter_conditions(company_id, status_code, query)
        stmt = (
            select(TreasuryTransfer)
            .where(*conditions)
            .options(
                selectinload(TreasuryTransfer.from_financial_account),
                selectinload(TreasuryTransfer.to_financial_account),
                selectinload(TreasuryTransfer.currency),
            )
            .order_by(TreasuryTransfer.transfer_date.desc(), TreasuryTransfer.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 1))
        )
        return list(self._session.scalars(stmt))

    def get_by_id(self, company_id: int, transfer_id: int) -> TreasuryTransfer | None:
        statement = select(TreasuryTransfer).where(
            TreasuryTransfer.company_id == company_id,
            TreasuryTransfer.id == transfer_id,
        )
        return self._session.scalar(statement)

    def get_detail(self, company_id: int, transfer_id: int) -> TreasuryTransfer | None:
        statement = select(TreasuryTransfer).where(
            TreasuryTransfer.company_id == company_id,
            TreasuryTransfer.id == transfer_id,
        ).options(
            selectinload(TreasuryTransfer.from_financial_account),
            selectinload(TreasuryTransfer.to_financial_account),
            selectinload(TreasuryTransfer.currency),
        )
        return self._session.scalar(statement)

    def add(self, entity: TreasuryTransfer) -> TreasuryTransfer:
        self._session.add(entity)
        return entity

    def save(self, entity: TreasuryTransfer) -> TreasuryTransfer:
        self._session.add(entity)
        return entity
