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
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
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
        tax_type_code: str | None = None,
        tax_point_start: date | None = None,
        tax_point_end: date | None = None,
        payment_date_start: date | None = None,
        payment_date_end: date | None = None,
    ) -> list[PostedTaxLineAggregate]:
        """Aggregate facts grouped by ``(tax_code_id, is_recoverable)``.

        T31: when ``tax_point_start/end`` are supplied, rows with a
        ``tax_point_date`` are filtered by that date; rows without one
        fall back to ``fiscal_period_id`` membership.

        T32 (cash-basis): when ``payment_date_start/end`` are supplied,
        filtering is purely by ``payment_date`` (ignores tax_point_date
        and fiscal_period_ids).
        """
        if (
            not fiscal_period_ids
            and not (tax_point_start and tax_point_end)
            and not (payment_date_start and payment_date_end)
        ):
            return []
        stmt = select(
            PostedTaxLine.tax_code_id,
            PostedTaxLine.is_recoverable,
            func.coalesce(func.sum(PostedTaxLine.taxable_base), 0),
            func.coalesce(func.sum(PostedTaxLine.tax_amount), 0),
        ).where(
            PostedTaxLine.company_id == company_id,
        )
        if payment_date_start is not None and payment_date_end is not None:
            # T32 cash-basis: filter strictly by payment_date.
            stmt = stmt.where(
                PostedTaxLine.payment_date.between(
                    payment_date_start, payment_date_end
                )
            )
        elif tax_point_start is not None and tax_point_end is not None:
            # T31 hybrid filter.
            from sqlalchemy import or_

            stmt = stmt.where(
                or_(
                    PostedTaxLine.tax_point_date.between(
                        tax_point_start, tax_point_end
                    ),
                    (PostedTaxLine.tax_point_date.is_(None))
                    & (
                        PostedTaxLine.fiscal_period_id.in_(
                            list(fiscal_period_ids)
                        )
                        if fiscal_period_ids
                        else PostedTaxLine.fiscal_period_id.is_(None)
                    ),
                )
            )
        else:
            stmt = stmt.where(
                PostedTaxLine.fiscal_period_id.in_(list(fiscal_period_ids))
            )
        stmt = stmt.group_by(
            PostedTaxLine.tax_code_id, PostedTaxLine.is_recoverable
        )
        if direction is not None:
            stmt = stmt.where(PostedTaxLine.direction == direction)
        if tax_type_code is not None:
            stmt = stmt.join(TaxCode, TaxCode.id == PostedTaxLine.tax_code_id).where(
                TaxCode.tax_type_code == tax_type_code,
            )
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

    def list_facts_for_line(
        self,
        company_id: int,
        fiscal_period_ids: Sequence[int],
        return_box_code: str,
        *,
        direction: str | None = None,
        limit: int = 500,
    ) -> list[PostedTaxLine]:
        """T40 drill-down: return raw facts contributing to a given return-box
        line code for the specified fiscal periods.

        Rows are joined to TaxCode on ``return_box_code``.
        """
        stmt = (
            select(PostedTaxLine)
            .join(TaxCode, TaxCode.id == PostedTaxLine.tax_code_id)
            .where(
                PostedTaxLine.company_id == company_id,
                PostedTaxLine.fiscal_period_id.in_(list(fiscal_period_ids)),
                TaxCode.return_box_code == return_box_code,
            )
            .order_by(PostedTaxLine.tax_point_date.asc(), PostedTaxLine.id.asc())
            .limit(limit)
        )
        if direction is not None:
            stmt = stmt.where(PostedTaxLine.direction == direction)
        return list(self._session.scalars(stmt))

    def stamp_payment_date_for_source_docs(
        self,
        company_id: int,
        source_document_type: str,
        source_document_ids: Sequence[int],
        payment_date: date,
    ) -> int:
        """T32: stamp payment_date on PTL rows whose payment_date is still NULL.

        Only rows with ``payment_date IS NULL`` are updated so that the
        first-payment date is preserved for cash-basis VAT aggregation.
        Returns the count of rows updated.
        """
        if not source_document_ids:
            return 0
        from sqlalchemy import update as _update

        stmt = (
            _update(PostedTaxLine)
            .where(
                PostedTaxLine.company_id == company_id,
                PostedTaxLine.source_document_type == source_document_type,
                PostedTaxLine.source_document_id.in_(list(source_document_ids)),
                PostedTaxLine.payment_date.is_(None),
            )
            .values(payment_date=payment_date)
        )
        result = self._session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    def aggregate_late_claims(
        self,
        company_id: int,
        before_date: date,
        *,
        direction: str | None = None,
        tax_type_code: str | None = None,
    ) -> list[PostedTaxLineAggregate]:
        """T42: aggregate facts that have a tax_point_date before ``before_date``
        but have never been included in a VAT return
        (``included_in_return_id IS NULL``).

        These are eligible late-claim rows that should be rolled into the
        current period's return.
        """
        stmt = select(
            PostedTaxLine.tax_code_id,
            PostedTaxLine.is_recoverable,
            func.coalesce(func.sum(PostedTaxLine.taxable_base), 0),
            func.coalesce(func.sum(PostedTaxLine.tax_amount), 0),
        ).where(
            PostedTaxLine.company_id == company_id,
            PostedTaxLine.tax_point_date < before_date,
            PostedTaxLine.tax_point_date.is_not(None),
            PostedTaxLine.included_in_return_id.is_(None),
        )
        if direction is not None:
            stmt = stmt.where(PostedTaxLine.direction == direction)
        if tax_type_code is not None:
            stmt = stmt.join(
                TaxCode, TaxCode.id == PostedTaxLine.tax_code_id
            ).where(TaxCode.tax_type_code == tax_type_code)
        stmt = stmt.group_by(
            PostedTaxLine.tax_code_id, PostedTaxLine.is_recoverable
        )
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

    def stamp_included_in_return(
        self,
        company_id: int,
        return_id: int,
        before_date: date,
        *,
        direction: str | None = None,
        tax_type_code: str | None = None,
    ) -> int:
        """T42: mark eligible late-claim rows as included in ``return_id``.

        Stamps ``included_in_return_id = return_id`` on every row that
        matches the same criteria as ``aggregate_late_claims``.
        Returns the count of rows stamped.
        """
        from sqlalchemy import update as _update

        stmt = (
            _update(PostedTaxLine)
            .where(
                PostedTaxLine.company_id == company_id,
                PostedTaxLine.tax_point_date < before_date,
                PostedTaxLine.tax_point_date.is_not(None),
                PostedTaxLine.included_in_return_id.is_(None),
            )
        )
        if direction is not None:
            stmt = stmt.where(PostedTaxLine.direction == direction)
        if tax_type_code is not None:
            stmt = stmt.where(
                PostedTaxLine.tax_code_id.in_(
                    select(TaxCode.id).where(
                        TaxCode.tax_type_code == tax_type_code
                    )
                )
            )
        stmt = stmt.values(included_in_return_id=return_id)
        result = self._session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    def clear_included_in_return(
        self,
        company_id: int,
        return_id: int,
    ) -> int:
        """T42: on redraft, clear ``included_in_return_id`` for rows stamped
        with this return_id so they can be re-evaluated.

        Returns the count of rows cleared.
        """
        from sqlalchemy import update as _update

        stmt = (
            _update(PostedTaxLine)
            .where(
                PostedTaxLine.company_id == company_id,
                PostedTaxLine.included_in_return_id == return_id,
            )
            .values(included_in_return_id=None)
        )
        result = self._session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]
