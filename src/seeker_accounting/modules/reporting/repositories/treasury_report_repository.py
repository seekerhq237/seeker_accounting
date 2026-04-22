from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from seeker_accounting.modules.treasury.models.financial_account import FinancialAccount
from seeker_accounting.modules.treasury.models.treasury_transaction import TreasuryTransaction
from seeker_accounting.modules.treasury.models.treasury_transfer import TreasuryTransfer

_RECEIPT_TYPES = {"cash_receipt", "bank_receipt"}


@dataclass(frozen=True, slots=True)
class TreasuryMovementSourceRow:
    financial_account_id: int
    account_code: str
    account_name: str
    account_type_code: str
    transaction_date: date
    document_number: str
    movement_type_label: str
    reference_text: str | None
    description: str | None
    signed_amount: Decimal
    journal_entry_id: int | None
    source_document_type: str
    source_document_id: int


class TreasuryReportRepository:
    """Query-only repository for treasury operational reporting."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_movement_rows(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
        financial_account_id: int | None = None,
    ) -> list[TreasuryMovementSourceRow]:
        rows = [
            *self._list_transaction_rows(company_id, date_from, date_to, financial_account_id),
            *self._list_transfer_rows(company_id, date_from, date_to, financial_account_id),
        ]
        rows.sort(
            key=lambda row: (
                row.account_name.lower(),
                row.account_code,
                row.transaction_date,
                row.document_number,
                row.source_document_id,
            )
        )
        return rows

    def _list_transaction_rows(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
        financial_account_id: int | None,
    ) -> list[TreasuryMovementSourceRow]:
        stmt = (
            select(
                TreasuryTransaction.id.label("document_id"),
                TreasuryTransaction.transaction_number.label("document_number"),
                TreasuryTransaction.transaction_date,
                TreasuryTransaction.transaction_type_code,
                TreasuryTransaction.reference_number,
                TreasuryTransaction.description,
                TreasuryTransaction.total_amount,
                TreasuryTransaction.posted_journal_entry_id.label("journal_entry_id"),
                FinancialAccount.id.label("financial_account_id"),
                FinancialAccount.account_code,
                FinancialAccount.name.label("account_name"),
                FinancialAccount.financial_account_type_code.label("account_type_code"),
            )
            .join(FinancialAccount, FinancialAccount.id == TreasuryTransaction.financial_account_id)
            .where(
                TreasuryTransaction.company_id == company_id,
                TreasuryTransaction.status_code == "posted",
            )
        )
        if isinstance(financial_account_id, int) and financial_account_id > 0:
            stmt = stmt.where(TreasuryTransaction.financial_account_id == financial_account_id)
        if date_from is not None:
            stmt = stmt.where(TreasuryTransaction.transaction_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(TreasuryTransaction.transaction_date <= date_to)
        rows: list[TreasuryMovementSourceRow] = []
        for row in self._session.execute(stmt):
            amount = self._to_decimal(row.total_amount)
            rows.append(
                TreasuryMovementSourceRow(
                    financial_account_id=int(row.financial_account_id),
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_type_code=row.account_type_code,
                    transaction_date=row.transaction_date,
                    document_number=row.document_number,
                    movement_type_label=row.transaction_type_code.replace("_", " ").title(),
                    reference_text=row.reference_number,
                    description=row.description,
                    signed_amount=amount if row.transaction_type_code in _RECEIPT_TYPES else (-amount).quantize(Decimal("0.01")),
                    journal_entry_id=row.journal_entry_id,
                    source_document_type="treasury_transaction",
                    source_document_id=int(row.document_id),
                )
            )
        return rows

    def _list_transfer_rows(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
        financial_account_id: int | None,
    ) -> list[TreasuryMovementSourceRow]:
        from_account = FinancialAccount.__table__.alias("from_account")
        to_account = FinancialAccount.__table__.alias("to_account")
        stmt = (
            select(
                TreasuryTransfer.id.label("document_id"),
                TreasuryTransfer.transfer_number.label("document_number"),
                TreasuryTransfer.transfer_date,
                TreasuryTransfer.reference_number,
                TreasuryTransfer.description,
                TreasuryTransfer.amount,
                TreasuryTransfer.posted_journal_entry_id.label("journal_entry_id"),
                from_account.c.id.label("from_account_id"),
                from_account.c.account_code.label("from_account_code"),
                from_account.c.name.label("from_account_name"),
                from_account.c.financial_account_type_code.label("from_account_type_code"),
                to_account.c.id.label("to_account_id"),
                to_account.c.account_code.label("to_account_code"),
                to_account.c.name.label("to_account_name"),
                to_account.c.financial_account_type_code.label("to_account_type_code"),
            )
            .join(from_account, from_account.c.id == TreasuryTransfer.from_financial_account_id)
            .join(to_account, to_account.c.id == TreasuryTransfer.to_financial_account_id)
            .where(
                TreasuryTransfer.company_id == company_id,
                TreasuryTransfer.status_code == "posted",
            )
        )
        if date_from is not None:
            stmt = stmt.where(TreasuryTransfer.transfer_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(TreasuryTransfer.transfer_date <= date_to)

        rows: list[TreasuryMovementSourceRow] = []
        for row in self._session.execute(stmt):
            amount = self._to_decimal(row.amount)
            if financial_account_id is None or financial_account_id == row.from_account_id:
                rows.append(
                    TreasuryMovementSourceRow(
                        financial_account_id=int(row.from_account_id),
                        account_code=row.from_account_code,
                        account_name=row.from_account_name,
                        account_type_code=row.from_account_type_code,
                        transaction_date=row.transfer_date,
                        document_number=row.document_number,
                        movement_type_label="Transfer Out",
                        reference_text=row.reference_number,
                        description=row.description,
                        signed_amount=(-amount).quantize(Decimal("0.01")),
                        journal_entry_id=row.journal_entry_id,
                        source_document_type="treasury_transfer",
                        source_document_id=int(row.document_id),
                    )
                )
            if financial_account_id is None or financial_account_id == row.to_account_id:
                rows.append(
                    TreasuryMovementSourceRow(
                        financial_account_id=int(row.to_account_id),
                        account_code=row.to_account_code,
                        account_name=row.to_account_name,
                        account_type_code=row.to_account_type_code,
                        transaction_date=row.transfer_date,
                        document_number=row.document_number,
                        movement_type_label="Transfer In",
                        reference_text=row.reference_number,
                        description=row.description,
                        signed_amount=amount,
                        journal_entry_id=row.journal_entry_id,
                        source_document_type="treasury_transfer",
                        source_document_id=int(row.document_id),
                    )
                )
        return rows

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
