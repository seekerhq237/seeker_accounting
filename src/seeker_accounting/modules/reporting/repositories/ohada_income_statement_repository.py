from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType


@dataclass(frozen=True, slots=True)
class OhadaAccountActivityRow:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_type_code: str | None
    normal_balance: str
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True, slots=True)
class OhadaChartAccountRow:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_type_code: str | None
    normal_balance: str
    is_active: bool


class OhadaIncomeStatementRepository:
    """Report-shaped OHADA income statement queries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_period_activity(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[OhadaAccountActivityRow]:
        conditions = [
            JournalEntry.company_id == company_id,
            JournalEntry.status_code == "POSTED",
            JournalEntry.posted_at.is_not(None),
        ]
        if date_from is not None:
            conditions.append(JournalEntry.entry_date >= date_from)
        if date_to is not None:
            conditions.append(JournalEntry.entry_date <= date_to)

        statement = (
            select(
                Account.id.label("account_id"),
                Account.account_code,
                Account.account_name,
                AccountClass.code.label("account_class_code"),
                AccountType.code.label("account_type_code"),
                Account.normal_balance,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("total_credit"),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .outerjoin(AccountClass, AccountClass.id == Account.account_class_id)
            .outerjoin(AccountType, AccountType.id == Account.account_type_id)
            .where(*conditions)
            .group_by(
                Account.id,
                Account.account_code,
                Account.account_name,
                AccountClass.code,
                AccountType.code,
                Account.normal_balance,
            )
            .order_by(Account.account_code.asc(), Account.id.asc())
        )

        rows: list[OhadaAccountActivityRow] = []
        for row in self._session.execute(statement):
            rows.append(
                OhadaAccountActivityRow(
                    account_id=int(row.account_id),
                    account_code=str(row.account_code),
                    account_name=str(row.account_name),
                    account_class_code=row.account_class_code,
                    account_type_code=row.account_type_code,
                    normal_balance=str(row.normal_balance),
                    total_debit=self._to_decimal(row.total_debit),
                    total_credit=self._to_decimal(row.total_credit),
                )
            )
        return rows

    def list_company_profit_and_loss_accounts(self, company_id: int) -> list[OhadaChartAccountRow]:
        statement = (
            select(
                Account.id.label("account_id"),
                Account.account_code,
                Account.account_name,
                AccountClass.code.label("account_class_code"),
                AccountType.code.label("account_type_code"),
                Account.normal_balance,
                Account.is_active,
            )
            .outerjoin(AccountClass, AccountClass.id == Account.account_class_id)
            .outerjoin(AccountType, AccountType.id == Account.account_type_id)
            .where(
                Account.company_id == company_id,
                or_(
                    Account.account_code.like("6%"),
                    Account.account_code.like("7%"),
                    Account.account_code.like("8%"),
                    AccountClass.code.in_(("6", "7", "8")),
                ),
            )
            .order_by(Account.account_code.asc(), Account.id.asc())
        )

        rows: list[OhadaChartAccountRow] = []
        for row in self._session.execute(statement):
            rows.append(
                OhadaChartAccountRow(
                    account_id=int(row.account_id),
                    account_code=str(row.account_code),
                    account_name=str(row.account_name),
                    account_class_code=row.account_class_code,
                    account_type_code=row.account_type_code,
                    normal_balance=str(row.normal_balance),
                    is_active=bool(row.is_active),
                )
            )
        return rows

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
