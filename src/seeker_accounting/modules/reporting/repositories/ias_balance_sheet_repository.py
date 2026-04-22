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
class IasBalanceSheetAccountRow:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_class_name: str | None
    account_type_code: str | None
    account_type_name: str | None
    account_type_section_code: str | None
    normal_balance: str
    is_active: bool
    allow_manual_posting: bool
    is_control_account: bool
    total_debit: Decimal
    total_credit: Decimal


class IasBalanceSheetRepository:
    """Report-shaped IAS/IFRS balance sheet queries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_balance_snapshot(
        self,
        company_id: int,
        statement_date: date | None,
    ) -> list[IasBalanceSheetAccountRow]:
        activity = (
            select(
                JournalEntryLine.account_id.label("account_id"),
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("total_credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                JournalEntry.posted_at.is_not(None),
            )
        )
        if statement_date is not None:
            activity = activity.where(JournalEntry.entry_date <= statement_date)
        activity = activity.group_by(JournalEntryLine.account_id).subquery()

        statement = (
            select(
                Account.id.label("account_id"),
                Account.account_code,
                Account.account_name,
                AccountClass.code.label("account_class_code"),
                AccountClass.name.label("account_class_name"),
                AccountType.code.label("account_type_code"),
                AccountType.name.label("account_type_name"),
                AccountType.financial_statement_section_code.label("account_type_section_code"),
                Account.normal_balance,
                Account.is_active,
                Account.allow_manual_posting,
                Account.is_control_account,
                func.coalesce(activity.c.total_debit, 0).label("total_debit"),
                func.coalesce(activity.c.total_credit, 0).label("total_credit"),
            )
            .outerjoin(activity, activity.c.account_id == Account.id)
            .outerjoin(AccountClass, AccountClass.id == Account.account_class_id)
            .outerjoin(AccountType, AccountType.id == Account.account_type_id)
            .where(
                Account.company_id == company_id,
                or_(
                    AccountClass.code.in_(("1", "2", "3", "4", "5")),
                    AccountType.financial_statement_section_code.in_(
                        ("ASSET", "LIABILITY", "EQUITY", "ASSET_LIABILITY")
                    ),
                    Account.account_code.like("1%"),
                    Account.account_code.like("2%"),
                    Account.account_code.like("3%"),
                    Account.account_code.like("4%"),
                    Account.account_code.like("5%"),
                ),
            )
            .order_by(Account.account_code.asc(), Account.id.asc())
        )

        rows: list[IasBalanceSheetAccountRow] = []
        for row in self._session.execute(statement):
            rows.append(
                IasBalanceSheetAccountRow(
                    account_id=int(row.account_id),
                    account_code=str(row.account_code),
                    account_name=str(row.account_name),
                    account_class_code=row.account_class_code,
                    account_class_name=row.account_class_name,
                    account_type_code=row.account_type_code,
                    account_type_name=row.account_type_name,
                    account_type_section_code=row.account_type_section_code,
                    normal_balance=str(row.normal_balance),
                    is_active=bool(row.is_active),
                    allow_manual_posting=bool(row.allow_manual_posting),
                    is_control_account=bool(row.is_control_account),
                    total_debit=self._to_decimal(row.total_debit),
                    total_credit=self._to_decimal(row.total_credit),
                )
            )
        return rows

    def sum_ytd_profit_loss(
        self,
        company_id: int,
        statement_date: date | None,
    ) -> Decimal:
        """Return YTD net P&L (credit minus debit) from posted class 6+7 activity."""
        stmt = (
            select(
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("total_credit"),
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("total_debit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(Account, Account.id == JournalEntryLine.account_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                JournalEntry.posted_at.is_not(None),
                or_(
                    Account.account_code.like("6%"),
                    Account.account_code.like("7%"),
                ),
            )
        )
        if statement_date is not None:
            stmt = stmt.where(JournalEntry.entry_date <= statement_date)
        row = self._session.execute(stmt).one()
        return (self._to_decimal(row.total_credit) - self._to_decimal(row.total_debit))

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
