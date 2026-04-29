"""Repository for ``PostedTaxLine``.

Read/write surface kept deliberately narrow:

* ``add`` / ``add_all`` — write new immutable rows at posting time.
* ``list_by_source`` — fetch the rows produced by a single source
  document (used to verify reversal symmetry from tests/diagnostics).
* ``list_for_period`` — drive VAT-return drafting and DSF aggregation
  by direction.
* ``aggregate_for_period`` — return summed taxable_base / tax_amount
  grouped by tax_code_id for a (company, fiscal_period, direction).

There are intentionally **no** ``save`` or ``update`` helpers — the
fact table is append-only.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.taxation.models.posted_tax_line import PostedTaxLine


class PostedTaxLineAggregate:
    """Lightweight aggregate row for VAT/DSF drafting."""

    __slots__ = ("tax_code_id", "is_recoverable", "taxable_base", "tax_amount")

    def __init__(
        self,
        tax_code_id: int | None,
        is_recoverable: bool | None,
        taxable_base: Decimal,
        tax_amount: Decimal,
    ) -> None:
        self.tax_code_id = tax_code_id
        self.is_recoverable = is_recoverable
        self.taxable_base = taxable_base
        self.tax_amount = tax_amount


class PostedTaxLineRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, fact: PostedTaxLine) -> PostedTaxLine:
        self._session.add(fact)
        return fact

    def add_all(self, facts: Iterable[PostedTaxLine]) -> None:
        self._session.add_all(list(facts))

    def list_by_source(
        self,
        company_id: int,
        source_document_type: str,
        source_document_id: int,
    ) -> list[PostedTaxLine]:
        stmt = (
            select(PostedTaxLine)
            .where(
                PostedTaxLine.company_id == company_id,
                PostedTaxLine.source_document_type == source_document_type,
                PostedTaxLine.source_document_id == source_document_id,
            )
            .order_by(PostedTaxLine.id.asc())
        )
        return list(self._session.scalars(stmt))

    def list_for_period(
        self,
        company_id: int,
        fiscal_period_id: int,
        *,
        direction: str | None = None,
    ) -> list[PostedTaxLine]:
        stmt = select(PostedTaxLine).where(
            PostedTaxLine.company_id == company_id,
            PostedTaxLine.fiscal_period_id == fiscal_period_id,
        )
        if direction is not None:
            stmt = stmt.where(PostedTaxLine.direction == direction)
        stmt = stmt.order_by(PostedTaxLine.id.asc())
        return list(self._session.scalars(stmt))

    def aggregate_for_period(
        self,
        company_id: int,
        fiscal_period_ids: Sequence[int],
        *,
        direction: str | None = None,
    ) -> list[PostedTaxLineAggregate]:
        if not fiscal_period_ids:
            return []
        stmt = (
            select(
                PostedTaxLine.tax_code_id,
                PostedTaxLine.is_recoverable,
                func.coalesce(func.sum(PostedTaxLine.taxable_base), 0),
                func.coalesce(func.sum(PostedTaxLine.tax_amount), 0),
            )
            .where(
                PostedTaxLine.company_id == company_id,
                PostedTaxLine.fiscal_period_id.in_(list(fiscal_period_ids)),
            )
            .group_by(PostedTaxLine.tax_code_id, PostedTaxLine.is_recoverable)
        )
        if direction is not None:
            stmt = stmt.where(PostedTaxLine.direction == direction)
        rows = self._session.execute(stmt).all()
        return [
            PostedTaxLineAggregate(
                tax_code_id=tc,
                is_recoverable=rec,
                taxable_base=Decimal(base),
                tax_amount=Decimal(tax),
            )
            for tc, rec, base, tax in rows
        ]
