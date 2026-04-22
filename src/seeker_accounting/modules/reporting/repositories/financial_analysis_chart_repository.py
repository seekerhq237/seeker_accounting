from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType


@dataclass(frozen=True, slots=True)
class ProfitLossMonthlyActivityRow:
    period_year: int
    period_month: int
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_type_section_code: str | None
    normal_balance: str | None
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True, slots=True)
class ProfitLossPeriodActivityRow:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_type_section_code: str | None
    normal_balance: str | None
    total_debit: Decimal
    total_credit: Decimal


class FinancialAnalysisChartRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_monthly_profit_loss_activity(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[ProfitLossMonthlyActivityRow]:
        stmt = (
            select(
                extract("year", JournalEntry.entry_date).label("period_year"),
                extract("month", JournalEntry.entry_date).label("period_month"),
                Account.id.label("account_id"),
                Account.account_code,
                Account.account_name,
                func.substr(Account.account_code, 1, 1).label("account_class_code"),
                AccountType.financial_statement_section_code.label("account_type_section_code"),
                Account.normal_balance,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("total_credit"),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(AccountType, AccountType.id == Account.account_type_id)
            .where(*self._base_conditions(company_id, date_from, date_to))
            .group_by(
                extract("year", JournalEntry.entry_date),
                extract("month", JournalEntry.entry_date),
                Account.id,
                Account.account_code,
                Account.account_name,
                func.substr(Account.account_code, 1, 1),
                AccountType.financial_statement_section_code,
                Account.normal_balance,
            )
            .order_by(
                extract("year", JournalEntry.entry_date).asc(),
                extract("month", JournalEntry.entry_date).asc(),
                Account.account_code.asc(),
            )
        )

        rows: list[ProfitLossMonthlyActivityRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                ProfitLossMonthlyActivityRow(
                    period_year=int(row.period_year),
                    period_month=int(row.period_month),
                    account_id=row.account_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_class_code=row.account_class_code,
                    account_type_section_code=row.account_type_section_code,
                    normal_balance=row.normal_balance,
                    total_debit=self._to_amount(row.total_debit),
                    total_credit=self._to_amount(row.total_credit),
                )
            )
        return rows

    def list_period_profit_loss_activity(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[ProfitLossPeriodActivityRow]:
        stmt = (
            select(
                Account.id.label("account_id"),
                Account.account_code,
                Account.account_name,
                func.substr(Account.account_code, 1, 1).label("account_class_code"),
                AccountType.financial_statement_section_code.label("account_type_section_code"),
                Account.normal_balance,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("total_credit"),
            )
            .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(AccountType, AccountType.id == Account.account_type_id)
            .where(*self._base_conditions(company_id, date_from, date_to))
            .group_by(
                Account.id,
                Account.account_code,
                Account.account_name,
                func.substr(Account.account_code, 1, 1),
                AccountType.financial_statement_section_code,
                Account.normal_balance,
            )
            .order_by(Account.account_code.asc())
        )

        rows: list[ProfitLossPeriodActivityRow] = []
        for row in self._session.execute(stmt):
            rows.append(
                ProfitLossPeriodActivityRow(
                    account_id=row.account_id,
                    account_code=row.account_code,
                    account_name=row.account_name,
                    account_class_code=row.account_class_code,
                    account_type_section_code=row.account_type_section_code,
                    normal_balance=row.normal_balance,
                    total_debit=self._to_amount(row.total_debit),
                    total_credit=self._to_amount(row.total_credit),
                )
            )
        return rows

    @staticmethod
    def _base_conditions(company_id: int, date_from: date | None, date_to: date | None) -> list[object]:
        conditions: list[object] = [
            Account.company_id == company_id,
            JournalEntry.company_id == company_id,
            JournalEntry.status_code == "POSTED",
            JournalEntry.posted_at.is_not(None),
        ]
        if date_from is not None:
            conditions.append(JournalEntry.entry_date >= date_from)
        if date_to is not None:
            conditions.append(JournalEntry.entry_date <= date_to)
        return conditions

    @staticmethod
    def _to_amount(value: object) -> Decimal:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
