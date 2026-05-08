"""Inventory Reconciliation Report Service.

Compares the stock ledger balance value with the GL account balance for each
inventory account to detect and surface any drift.

Logic:
  - For each item's inventory_account_id, sum GL posted JE lines (Dr - Cr)
  - For each item, sum stock ledger balance value
  - Difference = reconciling item (should be zero in a clean state)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.inventory.models.item import Item
from seeker_accounting.modules.inventory.models.stock_ledger_balance import StockLedgerBalance

_ZERO = Decimal("0")


@dataclass
class ReconciliationRowDTO:
    account_id: int
    account_code: str | None
    account_name: str | None
    gl_balance: Decimal
    stock_ledger_value: Decimal
    difference: Decimal
    is_reconciled: bool


@dataclass
class InventoryReconciliationReportDTO:
    as_of_date: date
    company_id: int
    rows: list[ReconciliationRowDTO]
    total_gl: Decimal
    total_stock_ledger: Decimal
    total_difference: Decimal


class InventoryReconciliationReportService:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = unit_of_work_factory

    def get_report(
        self, company_id: int, as_of_date: date | None = None
    ) -> InventoryReconciliationReportDTO:
        today = as_of_date or date.today()
        with self._uow_factory() as uow:
            return self._build(uow.session, company_id, today)

    def _build(
        self, session: Session, company_id: int, as_of_date: date
    ) -> InventoryReconciliationReportDTO:
        from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
        from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
        from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account

        # 1. Inventory account IDs used by items
        inv_account_ids: set[int] = set(
            row.inventory_account_id
            for row in session.scalars(
                select(Item).where(
                    Item.company_id == company_id,
                    Item.inventory_account_id.isnot(None),
                )
            )
            if row.inventory_account_id
        )
        if not inv_account_ids:
            return InventoryReconciliationReportDTO(
                as_of_date=as_of_date,
                company_id=company_id,
                rows=[],
                total_gl=_ZERO,
                total_stock_ledger=_ZERO,
                total_difference=_ZERO,
            )

        # 2. GL net balances per inventory account (posted, up to as_of_date)
        gl_stmt = (
            select(
                JournalEntryLine.account_id,
                func.sum(
                    JournalEntryLine.debit_amount - JournalEntryLine.credit_amount
                ).label("net_balance"),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "posted",
                JournalEntry.entry_date <= as_of_date,
                JournalEntryLine.account_id.in_(inv_account_ids),
            )
            .group_by(JournalEntryLine.account_id)
        )
        gl_by_account: dict[int, Decimal] = {
            row.account_id: Decimal(str(row.net_balance or 0))
            for row in session.execute(gl_stmt)
        }

        # 3. Stock ledger values per inventory account
        # Map item_id -> inventory_account_id
        item_account_map: dict[int, int] = {}
        for row in session.scalars(
            select(Item).where(
                Item.company_id == company_id,
                Item.inventory_account_id.isnot(None),
            )
        ):
            item_account_map[row.id] = row.inventory_account_id

        sl_by_account: dict[int, Decimal] = {}
        for bal in session.scalars(
            select(StockLedgerBalance).where(
                StockLedgerBalance.company_id == company_id,
                StockLedgerBalance.quantity > 0,
            )
        ):
            acc_id = item_account_map.get(bal.item_id)
            if acc_id:
                sl_by_account[acc_id] = sl_by_account.get(acc_id, _ZERO) + Decimal(str(bal.value))

        # 4. Account metadata
        all_account_ids = inv_account_ids | set(gl_by_account) | set(sl_by_account)
        accts = {
            row.id: (row.account_code, row.account_name)
            for row in session.scalars(
                select(Account).where(Account.id.in_(all_account_ids))
            )
        }

        # 5. Build rows
        rows: list[ReconciliationRowDTO] = []
        total_gl = _ZERO
        total_sl = _ZERO

        for acc_id in sorted(all_account_ids):
            gl = gl_by_account.get(acc_id, _ZERO)
            sl = sl_by_account.get(acc_id, _ZERO)
            diff = gl - sl
            code, name = accts.get(acc_id, (None, None))
            rows.append(
                ReconciliationRowDTO(
                    account_id=acc_id,
                    account_code=code,
                    account_name=name,
                    gl_balance=gl,
                    stock_ledger_value=sl,
                    difference=diff,
                    is_reconciled=abs(diff) < Decimal("0.01"),
                )
            )
            total_gl += gl
            total_sl += sl

        return InventoryReconciliationReportDTO(
            as_of_date=as_of_date,
            company_id=company_id,
            rows=rows,
            total_gl=total_gl,
            total_stock_ledger=total_sl,
            total_difference=total_gl - total_sl,
        )
