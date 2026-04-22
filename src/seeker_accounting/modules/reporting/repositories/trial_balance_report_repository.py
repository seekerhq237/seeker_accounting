from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine


@dataclass(frozen=True, slots=True)
class TrialBalanceRow:
    account_id: int
    account_code: str
    account_name: str
    opening_debit: Decimal
    opening_credit: Decimal
    period_debit: Decimal
    period_credit: Decimal


class TrialBalanceReportRepository:
    """Report-shaped queries for the trial balance."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_account_activity(
        self,
        company_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[TrialBalanceRow]:
        """Return per-account opening and period totals derived from posted journals."""

        opening_map = {}
        if date_from is not None:
            opening_map = self._aggregate(
                company_id=company_id,
                lower_date=None,
                upper_date=date_from,
                include_upper=False,
            )

        period_map = self._aggregate(
            company_id=company_id,
            lower_date=date_from,
            upper_date=date_to,
            include_upper=True,
        )

        account_ids = set(opening_map.keys()) | set(period_map.keys())
        rows: list[TrialBalanceRow] = []
        for account_id in sorted(account_ids):
            base = opening_map.get(account_id) or period_map.get(account_id)
            if base is None:
                continue
            account_code, account_name = base["account_code"], base["account_name"]
            opening_debit = opening_map.get(account_id, {}).get("debit", Decimal("0.00"))
            opening_credit = opening_map.get(account_id, {}).get("credit", Decimal("0.00"))
            period_debit = period_map.get(account_id, {}).get("debit", Decimal("0.00"))
            period_credit = period_map.get(account_id, {}).get("credit", Decimal("0.00"))

            rows.append(
                TrialBalanceRow(
                    account_id=account_id,
                    account_code=account_code,
                    account_name=account_name,
                    opening_debit=opening_debit,
                    opening_credit=opening_credit,
                    period_debit=period_debit,
                    period_credit=period_credit,
                )
            )

        rows.sort(key=lambda row: (row.account_code, row.account_id))
        return rows

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        company_id: int,
        lower_date: date | None,
        upper_date: date | None,
        include_upper: bool,
    ) -> dict[int, dict[str, Decimal | str]]:
        """Aggregate debit/credit totals grouped by account."""
        conditions = [
            JournalEntry.company_id == company_id,
            JournalEntry.status_code == "POSTED",
            JournalEntry.posted_at.is_not(None),
        ]
        if lower_date is not None:
            conditions.append(JournalEntry.entry_date >= lower_date)
        if upper_date is not None:
            if include_upper:
                conditions.append(JournalEntry.entry_date <= upper_date)
            else:
                conditions.append(JournalEntry.entry_date < upper_date)

        statement = (
            select(
                Account.id.label("account_id"),
                Account.account_code,
                Account.account_name,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("credit"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .join(Account, Account.id == JournalEntryLine.account_id)
            .where(*conditions)
            .group_by(Account.id, Account.account_code, Account.account_name)
        )

        result: dict[int, dict[str, Decimal | str]] = {}
        for row in self._session.execute(statement):
            account_id = int(row.account_id)
            result[account_id] = {
                "account_code": row.account_code,
                "account_name": row.account_name,
                "debit": self._to_decimal(row.debit),
                "credit": self._to_decimal(row.credit),
            }
        return result

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
