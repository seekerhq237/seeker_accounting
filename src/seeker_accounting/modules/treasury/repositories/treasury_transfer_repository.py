from __future__ import annotations

from sqlalchemy import select
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
