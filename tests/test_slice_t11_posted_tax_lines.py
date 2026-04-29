"""Slice T11 tests — PostedTaxLine fact table + TaxFactService.

These tests exercise the immutable tax-fact write path against an
in-memory SQLite database. They verify:

  * record_facts_in_session inserts one row per non-zero-tax line
  * sales-direction posts are positive; credit-note posts (caller-
    signed) are negative — net = SUM is therefore correct
  * unsupported direction codes are rejected
  * lines with no tax_code and zero tax are skipped
  * list_facts_for_source returns rows in id order
  * aggregate_for_period collapses by (tax_code_id, is_recoverable)
  * the model has no updated_at column (immutability invariant)
"""

from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db import model_registry  # noqa: F401  -- ensures all models register
from seeker_accounting.db.base import Base
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    DIRECTION_SALES,
    SOURCE_PURCHASE_BILL,
    SOURCE_SALES_CREDIT_NOTE,
    SOURCE_SALES_INVOICE,
    PostedTaxLine,
)
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineRepository,
)
from seeker_accounting.modules.taxation.services.tax_fact_service import (
    TaxFactInput,
    TaxFactService,
)


def _make_session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )


def _seed_minimum_fk_targets(session: Session) -> tuple[int, int, int, int]:
    """Insert a Company, FiscalYear, FiscalPeriod, JournalEntry and
    return their ids.  Uses raw INSERT through the underlying tables
    to avoid pulling in unrelated services.
    """
    from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import (
        FiscalPeriod,
    )
    from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import (
        FiscalYear,
    )
    from seeker_accounting.modules.accounting.journals.models.journal_entry import (
        JournalEntry,
    )
    from seeker_accounting.modules.companies.models.company import Company

    company = Company(
        legal_name="Test Co",
        display_name="Test",
        registration_number=None,
        tax_identifier=None,
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()

    fy = FiscalYear(
        company_id=company.id,
        year_code="FY2026",
        year_name="Fiscal Year 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status_code="OPEN",
    )
    session.add(fy)
    session.flush()

    fp = FiscalPeriod(
        company_id=company.id,
        fiscal_year_id=fy.id,
        period_number=1,
        period_code="FY2026-M01",
        period_name="January 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        status_code="OPEN",
    )
    session.add(fp)
    session.flush()

    je = JournalEntry(
        company_id=company.id,
        fiscal_period_id=fp.id,
        entry_number="JE-0001",
        entry_date=date(2026, 1, 15),
        journal_type_code="SALES",
        reference_text="ref",
        description="desc",
        source_module_code="sales",
        source_document_type="sales_invoice",
        source_document_id=1,
        status_code="POSTED",
        posted_at=datetime(2026, 1, 15, 10, 0, 0),
    )
    session.add(je)
    session.flush()
    return company.id, fy.id, fp.id, je.id


class PostedTaxLineModelTests(unittest.TestCase):
    def test_model_has_no_updated_at_column(self) -> None:
        """Immutability invariant: rows must never be updated, so the
        TimestampMixin (which adds updated_at) must NOT be applied."""
        cols = {c.name for c in PostedTaxLine.__table__.columns}
        self.assertIn("created_at", cols)
        self.assertNotIn("updated_at", cols)


class TaxFactServiceWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._session_factory = _make_session_factory()
        self._service = TaxFactService(
            posted_tax_line_repository_factory=PostedTaxLineRepository,
        )

    def _open_session(self) -> Session:
        return self._session_factory()

    def test_records_one_fact_per_taxed_line(self) -> None:
        with self._open_session() as session:
            company_id, _, fp_id, je_id = _seed_minimum_fk_targets(session)
            inputs = [
                TaxFactInput(
                    tax_code_id=None,
                    taxable_base=Decimal("100.00"),
                    tax_amount=Decimal("19.25"),
                    is_recoverable=None,
                    source_line_id=11,
                ),
                TaxFactInput(
                    tax_code_id=None,
                    taxable_base=Decimal("50.00"),
                    tax_amount=Decimal("9.63"),
                    is_recoverable=None,
                    source_line_id=12,
                ),
            ]

            count = self._service.record_facts_in_session(
                session,
                company_id=company_id,
                fiscal_period_id=fp_id,
                direction=DIRECTION_SALES,
                source_document_type=SOURCE_SALES_INVOICE,
                source_document_id=1,
                journal_entry_id=je_id,
                posted_at=datetime(2026, 1, 15, 10, 0, 0),
                posted_by_user_id=None,
                line_facts=inputs,
            )
            session.commit()

            self.assertEqual(count, 2)
            rows = self._service.list_facts_for_source(
                session, company_id, SOURCE_SALES_INVOICE, 1
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0].direction, DIRECTION_SALES)
            self.assertEqual(rows[0].taxable_base, Decimal("100.00"))
            self.assertEqual(rows[0].tax_amount, Decimal("19.25"))
            self.assertEqual(rows[1].source_line_id, 12)

    def test_skips_lines_with_no_tax_code_and_zero_tax(self) -> None:
        with self._open_session() as session:
            company_id, _, fp_id, je_id = _seed_minimum_fk_targets(session)
            inputs = [
                TaxFactInput(
                    tax_code_id=None,
                    taxable_base=Decimal("100.00"),
                    tax_amount=Decimal("0.00"),
                    is_recoverable=None,
                    source_line_id=21,
                ),
            ]
            count = self._service.record_facts_in_session(
                session,
                company_id=company_id,
                fiscal_period_id=fp_id,
                direction=DIRECTION_SALES,
                source_document_type=SOURCE_SALES_INVOICE,
                source_document_id=2,
                journal_entry_id=je_id,
                posted_at=datetime(2026, 1, 15, 10, 0, 0),
                posted_by_user_id=None,
                line_facts=inputs,
            )
            session.commit()
            self.assertEqual(count, 0)
            self.assertEqual(
                self._service.list_facts_for_source(
                    session, company_id, SOURCE_SALES_INVOICE, 2
                ),
                [],
            )

    def test_rejects_unknown_direction(self) -> None:
        with self._open_session() as session:
            company_id, _, fp_id, je_id = _seed_minimum_fk_targets(session)
            with self.assertRaises(ValueError):
                self._service.record_facts_in_session(
                    session,
                    company_id=company_id,
                    fiscal_period_id=fp_id,
                    direction="UNKNOWN",
                    source_document_type=SOURCE_SALES_INVOICE,
                    source_document_id=3,
                    journal_entry_id=je_id,
                    posted_at=datetime(2026, 1, 15, 10, 0, 0),
                    posted_by_user_id=None,
                    line_facts=[
                        TaxFactInput(
                            tax_code_id=None,
                            taxable_base=Decimal("1.00"),
                            tax_amount=Decimal("1.00"),
                            is_recoverable=None,
                            source_line_id=None,
                        )
                    ],
                )


class TaxFactReversalSemanticsTests(unittest.TestCase):
    """Credit notes write signed-negative facts so SUM gives net."""

    def setUp(self) -> None:
        self._session_factory = _make_session_factory()
        self._service = TaxFactService(
            posted_tax_line_repository_factory=PostedTaxLineRepository,
        )

    def test_invoice_then_credit_note_net_to_zero(self) -> None:
        with self._session_factory() as session:
            company_id, _, fp_id, je_id = _seed_minimum_fk_targets(session)

            # Invoice posts positive
            self._service.record_facts_in_session(
                session,
                company_id=company_id,
                fiscal_period_id=fp_id,
                direction=DIRECTION_SALES,
                source_document_type=SOURCE_SALES_INVOICE,
                source_document_id=10,
                journal_entry_id=je_id,
                posted_at=datetime(2026, 1, 15, 10, 0, 0),
                posted_by_user_id=None,
                line_facts=[
                    TaxFactInput(
                        tax_code_id=None,
                        taxable_base=Decimal("200.00"),
                        tax_amount=Decimal("38.50"),
                        is_recoverable=None,
                        source_line_id=1,
                    )
                ],
            )

            # Full credit note posts NEGATIVE
            self._service.record_facts_in_session(
                session,
                company_id=company_id,
                fiscal_period_id=fp_id,
                direction=DIRECTION_SALES,
                source_document_type=SOURCE_SALES_CREDIT_NOTE,
                source_document_id=11,
                journal_entry_id=je_id,
                posted_at=datetime(2026, 1, 16, 10, 0, 0),
                posted_by_user_id=None,
                line_facts=[
                    TaxFactInput(
                        tax_code_id=None,
                        taxable_base=Decimal("-200.00"),
                        tax_amount=Decimal("-38.50"),
                        is_recoverable=None,
                        source_line_id=1,
                    )
                ],
            )
            session.commit()

            # Aggregate for the period yields net zero
            repo = PostedTaxLineRepository(session)
            agg = repo.aggregate_for_period(
                company_id, [fp_id], direction=DIRECTION_SALES
            )
            self.assertEqual(len(agg), 1)
            self.assertEqual(agg[0].taxable_base, Decimal("0.00"))
            self.assertEqual(agg[0].tax_amount, Decimal("0.00"))


class PostedTaxLineRepositoryAggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._session_factory = _make_session_factory()

    def test_aggregate_groups_by_tax_code_and_recoverable(self) -> None:
        with self._session_factory() as session:
            company_id, _, fp_id, je_id = _seed_minimum_fk_targets(session)
            repo = PostedTaxLineRepository(session)

            # Two purchase facts, one recoverable, one non-recoverable
            now = datetime(2026, 1, 15, 10, 0, 0)
            repo.add_all(
                [
                    PostedTaxLine(
                        company_id=company_id,
                        fiscal_period_id=fp_id,
                        direction=DIRECTION_PURCHASE,
                        source_document_type=SOURCE_PURCHASE_BILL,
                        source_document_id=100,
                        source_line_id=1,
                        journal_entry_id=je_id,
                        tax_code_id=None,
                        taxable_base=Decimal("500.00"),
                        tax_amount=Decimal("96.25"),
                        is_recoverable=True,
                        posted_at=now,
                        posted_by_user_id=None,
                    ),
                    PostedTaxLine(
                        company_id=company_id,
                        fiscal_period_id=fp_id,
                        direction=DIRECTION_PURCHASE,
                        source_document_type=SOURCE_PURCHASE_BILL,
                        source_document_id=100,
                        source_line_id=2,
                        journal_entry_id=je_id,
                        tax_code_id=None,
                        taxable_base=Decimal("100.00"),
                        tax_amount=Decimal("19.25"),
                        is_recoverable=False,
                        posted_at=now,
                        posted_by_user_id=None,
                    ),
                ]
            )
            session.commit()

            result = repo.aggregate_for_period(
                company_id, [fp_id], direction=DIRECTION_PURCHASE
            )
            by_recoverable = {row.is_recoverable: row for row in result}
            self.assertEqual(by_recoverable[True].taxable_base, Decimal("500.00"))
            self.assertEqual(by_recoverable[True].tax_amount, Decimal("96.25"))
            self.assertEqual(by_recoverable[False].taxable_base, Decimal("100.00"))
            self.assertEqual(by_recoverable[False].tax_amount, Decimal("19.25"))


class PostedTaxLineSchemaTests(unittest.TestCase):
    def test_indexes_present(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        insp = inspect(engine)
        idx_names = {idx["name"] for idx in insp.get_indexes("posted_tax_lines")}
        self.assertIn("ix_posted_tax_lines_company_id", idx_names)
        self.assertIn("ix_posted_tax_lines_company_period_direction", idx_names)
        self.assertIn("ix_posted_tax_lines_source", idx_names)
        self.assertIn("ix_posted_tax_lines_company_tax_code", idx_names)


if __name__ == "__main__":
    unittest.main()
