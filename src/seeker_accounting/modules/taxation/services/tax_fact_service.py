"""TaxFactService — record immutable tax facts inside posting transactions.

This service is an in-transaction collaborator for the posting
services (sales invoices, sales credit notes, purchase bills, purchase
credit notes).  It:

* writes one ``PostedTaxLine`` per source line that carries a tax
  obligation;
* writes signed-negative amounts on credit-note posting so that a
  plain ``SUM(...)`` across a fiscal period yields the correct net
  taxable base / net tax for VAT-return drafting and DSF aggregation;
* never opens its own unit of work — the calling posting service
  already manages the transaction boundary, and the fact rows must
  commit atomically with the journal entry that produced them.

Because this service is invoked from already-permission-gated posting
services, it does not perform its own permission checks.  The caller
is the trust boundary; the fact table is an internal artefact that
mirrors what the journal already represents.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    DIRECTION_SALES,
    PostedTaxLine,
)
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineRepository,
)


PostedTaxLineRepositoryFactory = Callable[[Session], PostedTaxLineRepository]


@dataclass(frozen=True, slots=True)
class TaxFactInput:
    """One line-level tax fact prepared by a posting service.

    ``taxable_base`` and ``tax_amount`` must already be signed by the
    caller — positive for forward posts (invoices/bills), negative for
    reversal posts (credit notes).
    """

    tax_code_id: int | None
    taxable_base: Decimal
    tax_amount: Decimal
    is_recoverable: bool | None
    source_line_id: int | None
    # T33: when True, record a paired SALES fact row (reverse-charge
    # self-assessment).  Caller sets this from the TaxCode flag.
    is_reverse_charge: bool = False
    # T44: multi-currency VAT. Populate these when the source document
    # was issued in a foreign currency.
    base_amount: Decimal | None = None
    tax_amount_reporting_currency: Decimal | None = None
    taxable_base_reporting_currency: Decimal | None = None
    exchange_rate: Decimal | None = None
    rate_source: str | None = None
    transaction_currency_code: str | None = None


class TaxFactService:
    """Append-only writer for the ``posted_tax_lines`` fact table."""

    _ALLOWED_DIRECTIONS = frozenset({DIRECTION_SALES, DIRECTION_PURCHASE})

    def __init__(
        self,
        posted_tax_line_repository_factory: PostedTaxLineRepositoryFactory,
    ) -> None:
        self._repository_factory = posted_tax_line_repository_factory

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def record_facts_in_session(
        self,
        session: Session,
        *,
        company_id: int,
        fiscal_period_id: int,
        direction: str,
        source_document_type: str,
        source_document_id: int,
        journal_entry_id: int,
        posted_at: datetime,
        posted_by_user_id: int | None,
        line_facts: Iterable[TaxFactInput],
        tax_point_date: date | None = None,
    ) -> int:
        """Insert one row per ``TaxFactInput`` carrying a tax amount.

        Returns the count of rows inserted.

        Lines whose ``tax_code_id`` is ``None`` and whose ``tax_amount``
        is zero are skipped — they carry no tax obligation worth
        recording as a fact.
        """
        if direction not in self._ALLOWED_DIRECTIONS:
            raise ValueError(
                f"TaxFactService.record_facts_in_session: unsupported direction "
                f"{direction!r}"
            )

        repo = self._repository_factory(session)
        rows: list[PostedTaxLine] = []
        for fact in line_facts:
            if fact.tax_code_id is None and fact.tax_amount == Decimal("0.00"):
                continue
            rows.append(
                PostedTaxLine(
                    company_id=company_id,
                    fiscal_period_id=fiscal_period_id,
                    direction=direction,
                    source_document_type=source_document_type,
                    source_document_id=source_document_id,
                    source_line_id=fact.source_line_id,
                    journal_entry_id=journal_entry_id,
                    tax_code_id=fact.tax_code_id,
                    taxable_base=fact.taxable_base,
                    tax_amount=fact.tax_amount,
                    is_recoverable=fact.is_recoverable,
                    is_reverse_charge=fact.is_reverse_charge,
                    tax_point_date=tax_point_date,
                    posted_at=posted_at,
                    posted_by_user_id=posted_by_user_id,
                    base_amount=fact.base_amount,
                    tax_amount_reporting_currency=fact.tax_amount_reporting_currency,
                    taxable_base_reporting_currency=fact.taxable_base_reporting_currency,
                    exchange_rate=fact.exchange_rate,
                    rate_source=fact.rate_source,
                    transaction_currency_code=fact.transaction_currency_code,
                )
            )
            # T33: for reverse-charge facts on the purchase side, also
            # write a SALES-direction fact row (self-assessed output VAT).
            # This means the company both collects the tax (output L36)
            # and deducts it (input L29/L37) — net zero for full recovery.
            if fact.is_reverse_charge and direction == DIRECTION_PURCHASE:
                rows.append(
                    PostedTaxLine(
                        company_id=company_id,
                        fiscal_period_id=fiscal_period_id,
                        direction=DIRECTION_SALES,
                        source_document_type=source_document_type,
                        source_document_id=source_document_id,
                        source_line_id=fact.source_line_id,
                        journal_entry_id=journal_entry_id,
                        tax_code_id=fact.tax_code_id,
                        taxable_base=fact.taxable_base,
                        tax_amount=fact.tax_amount,
                        is_recoverable=None,  # output VAT — not a recovery
                        is_reverse_charge=True,
                        tax_point_date=tax_point_date,
                        posted_at=posted_at,
                        posted_by_user_id=posted_by_user_id,
                        base_amount=fact.base_amount,
                        tax_amount_reporting_currency=fact.tax_amount_reporting_currency,
                        taxable_base_reporting_currency=fact.taxable_base_reporting_currency,
                        exchange_rate=fact.exchange_rate,
                        rate_source=fact.rate_source,
                        transaction_currency_code=fact.transaction_currency_code,
                    )
                )

        if not rows:
            return 0
        repo.add_all(rows)
        # Ensure FK targets resolve and any unique-index violations
        # surface inside the caller's transaction boundary.
        session.flush()
        return len(rows)

    # ------------------------------------------------------------------
    # Read path (diagnostics / tests / VAT-return drafting)
    # ------------------------------------------------------------------

    def list_facts_for_source(
        self,
        session: Session,
        company_id: int,
        source_document_type: str,
        source_document_id: int,
    ) -> list[PostedTaxLine]:
        repo = self._repository_factory(session)
        return repo.list_by_source(company_id, source_document_type, source_document_id)
