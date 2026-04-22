from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from seeker_accounting.modules.treasury.models.bank_statement_import_batch import BankStatementImportBatch


class BankStatementImportBatchRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_company(
        self,
        company_id: int,
        financial_account_id: int | None = None,
    ) -> list[BankStatementImportBatch]:
        statement = select(BankStatementImportBatch).where(
            BankStatementImportBatch.company_id == company_id
        )
        if financial_account_id is not None:
            statement = statement.where(BankStatementImportBatch.financial_account_id == financial_account_id)
        statement = statement.order_by(BankStatementImportBatch.imported_at.desc())
        return list(self._session.scalars(statement))

    def get_by_id(self, company_id: int, batch_id: int) -> BankStatementImportBatch | None:
        statement = select(BankStatementImportBatch).where(
            BankStatementImportBatch.company_id == company_id,
            BankStatementImportBatch.id == batch_id,
        ).options(selectinload(BankStatementImportBatch.lines))
        return self._session.scalar(statement)

    def add(self, entity: BankStatementImportBatch) -> BankStatementImportBatch:
        self._session.add(entity)
        return entity
