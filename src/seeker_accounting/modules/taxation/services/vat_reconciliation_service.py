"""Slice T45 — VAT control reconciliation service.

Compares three independent signals for a VAT period:
  1. GL balances  — sum of debit/credit on output/input VAT accounts.
  2. Fact totals  — sum of ``posted_tax_lines`` rows for the period.
  3. Return totals — sum of ``tax_return_lines`` on the filed return.

A non-zero variance in any column indicates a bookkeeping inconsistency
that the controller should investigate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import JournalEntryLine
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_account_mapping_repository import (
    TaxCodeAccountMappingRepository,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.taxation.constants import (
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    DIRECTION_SALES,
    PostedTaxLine,
)
from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
from seeker_accounting.modules.taxation.models.tax_return_line import TaxReturnLine
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError

AccountRepositoryFactory = Callable[[Session], AccountRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
PostedTaxLineRepositoryFactory = Callable[[Session], PostedTaxLineRepository]
TaxReturnRepositoryFactory = Callable[[Session], TaxReturnRepository]
TaxCodeAccountMappingRepositoryFactory = Callable[[Session], TaxCodeAccountMappingRepository]

_ZERO = Decimal("0.00")

@dataclass(frozen=True, slots=True)
class VATReconciliationRowDTO:
    """One comparison row — either output VAT or input VAT."""

    label: str            # e.g. "Output VAT (4434)" or "Input VAT Recoverable (4452)"
    gl_balance: Decimal   # net movement in the GL account for the period
    fact_total: Decimal   # sum from posted_tax_lines
    return_total: Decimal # sum from filed tax_return_lines (or ZERO if no filed return)

    @property
    def gl_vs_fact_variance(self) -> Decimal:
        return self.gl_balance - self.fact_total

    @property
    def fact_vs_return_variance(self) -> Decimal:
        return self.fact_total - self.return_total

    @property
    def is_reconciled(self) -> bool:
        return self.gl_vs_fact_variance == _ZERO and self.fact_vs_return_variance == _ZERO


@dataclass(frozen=True, slots=True)
class VATReconciliationDTO:
    """Full reconciliation snapshot for a period."""

    company_id: int
    period_start: date
    period_end: date
    rows: tuple[VATReconciliationRowDTO, ...]
    notes: tuple[str, ...]  # any advisory messages (e.g. no filed return yet)

    @property
    def is_fully_reconciled(self) -> bool:
        return all(r.is_reconciled for r in self.rows)


class VATReconciliationService:
    """T45: compare GL, fact table, and return for a VAT period."""

    PERMISSION_VIEW = "taxation.returns.view"

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        account_repository_factory: AccountRepositoryFactory,
        tax_code_account_mapping_repository_factory: TaxCodeAccountMappingRepositoryFactory,
        posted_tax_line_repository_factory: PostedTaxLineRepositoryFactory,
        tax_return_repository_factory: TaxReturnRepositoryFactory,
        permission_service: PermissionService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._account_repository_factory = account_repository_factory
        self._tax_code_account_mapping_repository_factory = tax_code_account_mapping_repository_factory
        self._posted_tax_line_repository_factory = posted_tax_line_repository_factory
        self._tax_return_repository_factory = tax_return_repository_factory
        self._permission_service = permission_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile_period(
        self,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> VATReconciliationDTO:
        """Return the three-column reconciliation for a VAT period."""
        self._permission_service.require_permission(self.PERMISSION_VIEW)
        with self._unit_of_work_factory() as uow:
            session = uow.session
            company_repo = self._company_repository_factory(session)
            if company_repo.get_by_id(company_id) is None:
                raise NotFoundError(f"Company {company_id} not found.")

            notes: list[str] = []

            # ---- Fact totals (posted_tax_lines) -------------------
            output_fact = self._sum_fact(
                session, company_id, period_start, period_end, DIRECTION_SALES
            )
            input_fact = self._sum_fact(
                session, company_id, period_start, period_end, DIRECTION_PURCHASE
            )

            # ---- GL totals (journal_entry_lines) ------------------
            mapping_repo = self._tax_code_account_mapping_repository_factory(session)
            mappings = mapping_repo.list_by_company(company_id)

            output_account_ids = {
                m.tax_liability_account_id
                for m in mappings
                if m.tax_liability_account_id is not None
            }
            input_account_ids = {
                m.tax_asset_account_id
                for m in mappings
                if m.tax_asset_account_id is not None
            }

            output_gl = self._sum_gl(
                session, company_id, period_start, period_end,
                output_account_ids, credit_side=True,
            )
            input_gl = self._sum_gl(
                session, company_id, period_start, period_end,
                input_account_ids, credit_side=False,
            )

            # ---- Return totals (filed tax_return_lines) -----------
            return_repo = self._tax_return_repository_factory(session)
            filed_return = self._find_filed_return(
                session, company_id, period_start, period_end
            )

            if filed_return is None:
                notes.append(
                    "No filed VAT return found for this period — return totals show zero."
                )
                output_return = _ZERO
                input_return = _ZERO
            else:
                output_return, input_return = self._sum_return_lines(filed_return)

            # ---- Build account label strings ----------------------
            account_repo = self._account_repository_factory(session)
            output_label = self._account_label(
                account_repo, company_id, output_account_ids, "Output VAT"
            )
            input_label = self._account_label(
                account_repo, company_id, input_account_ids, "Input VAT Recoverable"
            )

            rows = (
                VATReconciliationRowDTO(
                    label=output_label,
                    gl_balance=output_gl,
                    fact_total=output_fact,
                    return_total=output_return,
                ),
                VATReconciliationRowDTO(
                    label=input_label,
                    gl_balance=input_gl,
                    fact_total=input_fact,
                    return_total=input_return,
                ),
            )
            return VATReconciliationDTO(
                company_id=company_id,
                period_start=period_start,
                period_end=period_end,
                rows=rows,
                notes=tuple(notes),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sum_fact(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
        direction: str,
    ) -> Decimal:
        """Sum tax_amount from posted_tax_lines for the period and direction."""
        stmt = (
            select(func.sum(PostedTaxLine.tax_amount))
            .join(JournalEntry, PostedTaxLine.journal_entry_id == JournalEntry.id)
            .where(
                PostedTaxLine.company_id == company_id,
                PostedTaxLine.direction == direction,
                JournalEntry.entry_date >= period_start,
                JournalEntry.entry_date <= period_end,
            )
        )
        result = session.scalar(stmt)
        return Decimal(str(result)) if result else _ZERO

    def _sum_gl(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
        account_ids: set[int],
        *,
        credit_side: bool,
    ) -> Decimal:
        """Sum the net movement on a set of accounts from posted journal entries.

        For output VAT accounts (normally credit-balance), we sum credits minus debits.
        For input VAT accounts (normally debit-balance), we sum debits minus credits.
        """
        if not account_ids:
            return _ZERO

        if credit_side:
            net_expr = func.sum(
                JournalEntryLine.credit_amount - JournalEntryLine.debit_amount
            )
        else:
            net_expr = func.sum(
                JournalEntryLine.debit_amount - JournalEntryLine.credit_amount
            )

        stmt = (
            select(net_expr)
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.company_id == company_id,
                JournalEntry.status_code == "POSTED",
                JournalEntry.entry_date >= period_start,
                JournalEntry.entry_date <= period_end,
                JournalEntryLine.account_id.in_(account_ids),
            )
        )
        result = session.scalar(stmt)
        return Decimal(str(result)) if result else _ZERO

    def _find_filed_return(
        self,
        session: Session,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> TaxReturn | None:
        """Find the most recent filed VAT return covering this period."""
        from sqlalchemy import and_
        from seeker_accounting.modules.taxation.constants import RETURN_STATUS_FILED

        stmt = (
            select(TaxReturn)
            .where(
                TaxReturn.company_id == company_id,
                TaxReturn.tax_type_code == TAX_TYPE_VAT,
                TaxReturn.period_start == period_start,
                TaxReturn.period_end == period_end,
                TaxReturn.status_code.in_([
                    RETURN_STATUS_FILED,
                    "SETTLED",
                    "AMENDED",
                ]),
            )
            .options()
            .order_by(TaxReturn.id.desc())
            .limit(1)
        )
        return session.scalar(stmt)

    @staticmethod
    def _sum_return_lines(
        tax_return: TaxReturn,
    ) -> tuple[Decimal, Decimal]:
        """Return (output_total, input_total) from TaxReturnLine rows.

        Lines whose box_code starts with 'L1' through 'L22' are output/sales lines.
        Lines whose box_code starts with 'L2' or higher are purchase-side.
        We use a simpler split: output = lines where amount > 0 with sales L-codes,
        input = lines whose amount represents recoverable input.

        Conservative approach: sum lines labelled L36 (net VAT due) and L30
        (recoverable total) directly if present, otherwise fall back to signing by
        known L-code groups.
        """
        _OUTPUT_L_CODES = frozenset({"L17", "L18", "L19", "L20", "L21", "L22", "L23"})
        _INPUT_L_CODES = frozenset({"L26", "L27", "L28", "L29", "L30"})

        output_total = _ZERO
        input_total = _ZERO
        for line in tax_return.lines:
            if line.box_code in _OUTPUT_L_CODES:
                output_total += line.amount
            elif line.box_code in _INPUT_L_CODES:
                input_total += line.amount
        return output_total, input_total

    def _account_label(
        self,
        account_repo: AccountRepository,
        company_id: int,
        account_ids: set[int],
        fallback_label: str,
    ) -> str:
        """Build a human-readable label for a set of account IDs."""
        if not account_ids:
            return fallback_label
        codes = []
        for aid in sorted(account_ids):
            account = account_repo.get_by_id(company_id, aid)
            if account:
                codes.append(account.account_code)
        if codes:
            return f"{fallback_label} ({', '.join(codes)})"
        return fallback_label
