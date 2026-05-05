"""Slice T44 tests — Multi-currency VAT columns on posted_tax_lines.

Validates:
* PostedTaxLine model accepts and persists T44 columns.
* TaxFactInput carries T44 fields.
* TaxFactService.record_facts_in_session() persists T44 fields on PostedTaxLine.
* T44 columns are nullable — domestic documents store NULL values.
"""
from __future__ import annotations

import datetime
import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db import model_registry  # noqa: F401 — registers all tables
from seeker_accounting.db.base import Base
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import FiscalYear
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_SALES,
    SOURCE_SALES_INVOICE,
    PostedTaxLine,
)
from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineRepository,
)
from seeker_accounting.modules.taxation.services.tax_fact_service import (
    TaxFactInput,
    TaxFactService,
)


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    return SF()


def _seed_company(session: Session) -> Company:
    co = Company(
        legal_name="T44 Test Co",
        display_name="T44TC",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(co)
    session.flush()
    return co


def _seed_fiscal_period(session: Session, company_id: int) -> FiscalPeriod:
    fy = FiscalYear(
        company_id=company_id,
        year_code="FY2025",
        year_name="FY 2025",
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 12, 31),
        status_code="OPEN",
    )
    session.add(fy)
    session.flush()

    fp = FiscalPeriod(
        company_id=company_id,
        fiscal_year_id=fy.id,
        period_number=1,
        period_code="2025-01",
        period_name="Jan 2025",
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 1, 31),
        status_code="OPEN",
    )
    session.add(fp)
    session.flush()
    return fp


def _seed_journal_entry(session: Session, company_id: int, fp_id: int) -> JournalEntry:
    je = JournalEntry(
        company_id=company_id,
        fiscal_period_id=fp_id,
        entry_date=datetime.date(2025, 1, 15),
        journal_type_code="SALES",
        reference_text="JE-001",
        description="Test JE",
        status_code="POSTED",
        source_document_type=SOURCE_SALES_INVOICE,
        source_document_id=1,
    )
    session.add(je)
    session.flush()
    return je


def _seed_tax_code(session: Session, company_id: int) -> TaxCode:
    tc = TaxCode(
        company_id=company_id,
        code="VAT19",
        name="Standard VAT 19.25%",
        tax_type_code="VAT",
        calculation_method_code="PERCENT",
        rate_percent=Decimal("19.25"),
        effective_from=datetime.date(2025, 1, 1),
    )
    session.add(tc)
    session.flush()
    return tc


class T44ModelColumnTests(unittest.TestCase):
    """PostedTaxLine model has T44 columns."""

    def setUp(self) -> None:
        self.session = _make_session()
        self.co = _seed_company(self.session)
        self.fp = _seed_fiscal_period(self.session, self.co.id)
        self.je = _seed_journal_entry(self.session, self.co.id, self.fp.id)
        self.tc = _seed_tax_code(self.session, self.co.id)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_foreign_currency_line_stores_t44_fields(self) -> None:
        """A foreign-currency PostedTaxLine round-trips all T44 columns."""
        line = PostedTaxLine(
            company_id=self.co.id,
            fiscal_period_id=self.fp.id,
            direction=DIRECTION_SALES,
            source_document_type=SOURCE_SALES_INVOICE,
            source_document_id=99,
            journal_entry_id=self.je.id,
            tax_code_id=self.tc.id,
            taxable_base=Decimal("500.00"),
            tax_amount=Decimal("96.25"),
            is_reverse_charge=False,
            posted_at=datetime.datetime.utcnow(),
            # T44 columns
            taxable_base_reporting_currency=Decimal("305000.00"),
            tax_amount_reporting_currency=Decimal("58712.50"),
            exchange_rate=Decimal("610.000000"),
            base_amount=Decimal("500.00"),
            rate_source="ECB",
            transaction_currency_code="USD",
        )
        self.session.add(line)
        self.session.commit()

        fetched = self.session.get(PostedTaxLine, line.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.taxable_base_reporting_currency, Decimal("305000.00"))
        self.assertEqual(fetched.tax_amount_reporting_currency, Decimal("58712.50"))
        self.assertEqual(fetched.exchange_rate, Decimal("610.000000"))
        self.assertEqual(fetched.rate_source, "ECB")
        self.assertEqual(fetched.transaction_currency_code, "USD")

    def test_domestic_line_has_null_t44_fields(self) -> None:
        """A domestic-currency PostedTaxLine stores NULL for T44 columns."""
        line = PostedTaxLine(
            company_id=self.co.id,
            fiscal_period_id=self.fp.id,
            direction=DIRECTION_SALES,
            source_document_type=SOURCE_SALES_INVOICE,
            source_document_id=100,
            journal_entry_id=self.je.id,
            tax_code_id=self.tc.id,
            taxable_base=Decimal("200.00"),
            tax_amount=Decimal("38.50"),
            is_reverse_charge=False,
            posted_at=datetime.datetime.utcnow(),
        )
        self.session.add(line)
        self.session.commit()

        fetched = self.session.get(PostedTaxLine, line.id)
        self.assertIsNone(fetched.taxable_base_reporting_currency)
        self.assertIsNone(fetched.tax_amount_reporting_currency)
        self.assertIsNone(fetched.exchange_rate)
        self.assertIsNone(fetched.rate_source)
        self.assertIsNone(fetched.transaction_currency_code)


class T44TaxFactInputTests(unittest.TestCase):
    """TaxFactInput carries T44 fields correctly."""

    def test_tax_fact_input_with_t44_fields(self) -> None:
        fact = TaxFactInput(
            tax_code_id=1,
            taxable_base=Decimal("500.00"),
            tax_amount=Decimal("96.25"),
            is_recoverable=None,
            source_line_id=10,
            taxable_base_reporting_currency=Decimal("305000.00"),
            tax_amount_reporting_currency=Decimal("58712.50"),
            exchange_rate=Decimal("610.000000"),
        )
        self.assertEqual(fact.taxable_base_reporting_currency, Decimal("305000.00"))
        self.assertEqual(fact.tax_amount_reporting_currency, Decimal("58712.50"))
        self.assertEqual(fact.exchange_rate, Decimal("610.000000"))

    def test_tax_fact_input_without_t44_fields_defaults_to_none(self) -> None:
        fact = TaxFactInput(
            tax_code_id=1,
            taxable_base=Decimal("200.00"),
            tax_amount=Decimal("38.50"),
            is_recoverable=None,
            source_line_id=None,
        )
        self.assertIsNone(fact.taxable_base_reporting_currency)
        self.assertIsNone(fact.tax_amount_reporting_currency)
        self.assertIsNone(fact.exchange_rate)


class T44TaxFactServiceTests(unittest.TestCase):
    """TaxFactService persists T44 fields on PostedTaxLine rows."""

    def setUp(self) -> None:
        self.session = _make_session()
        self.co = _seed_company(self.session)
        self.fp = _seed_fiscal_period(self.session, self.co.id)
        self.je = _seed_journal_entry(self.session, self.co.id, self.fp.id)
        self.tc = _seed_tax_code(self.session, self.co.id)
        self.session.commit()
        self.service = TaxFactService(
            posted_tax_line_repository_factory=PostedTaxLineRepository,
        )

    def tearDown(self) -> None:
        self.session.close()

    def test_record_facts_persists_t44_reporting_currency_fields(self) -> None:
        facts = [
            TaxFactInput(
                tax_code_id=self.tc.id,
                taxable_base=Decimal("500.00"),
                tax_amount=Decimal("96.25"),
                is_recoverable=None,
                source_line_id=None,
                taxable_base_reporting_currency=Decimal("305000.00"),
                tax_amount_reporting_currency=Decimal("58712.50"),
                exchange_rate=Decimal("610.000000"),
            )
        ]
        count = self.service.record_facts_in_session(
            self.session,
            company_id=self.co.id,
            fiscal_period_id=self.fp.id,
            direction=DIRECTION_SALES,
            source_document_type=SOURCE_SALES_INVOICE,
            source_document_id=50,
            journal_entry_id=self.je.id,
            posted_at=datetime.datetime.utcnow(),
            posted_by_user_id=None,
            line_facts=facts,
            tax_point_date=datetime.date(2025, 1, 15),
        )
        self.assertEqual(count, 1)
        self.session.commit()

        line = (
            self.session.query(PostedTaxLine)
            .filter_by(company_id=self.co.id, source_document_id=50)
            .one()
        )
        self.assertEqual(line.taxable_base_reporting_currency, Decimal("305000.00"))
        self.assertEqual(line.tax_amount_reporting_currency, Decimal("58712.50"))
        self.assertEqual(line.exchange_rate, Decimal("610.000000"))

    def test_record_facts_null_t44_for_domestic_currency(self) -> None:
        facts = [
            TaxFactInput(
                tax_code_id=self.tc.id,
                taxable_base=Decimal("200.00"),
                tax_amount=Decimal("38.50"),
                is_recoverable=None,
                source_line_id=None,
            )
        ]
        self.service.record_facts_in_session(
            self.session,
            company_id=self.co.id,
            fiscal_period_id=self.fp.id,
            direction=DIRECTION_SALES,
            source_document_type=SOURCE_SALES_INVOICE,
            source_document_id=51,
            journal_entry_id=self.je.id,
            posted_at=datetime.datetime.utcnow(),
            posted_by_user_id=None,
            line_facts=facts,
            tax_point_date=datetime.date(2025, 1, 15),
        )
        self.session.commit()

        line = (
            self.session.query(PostedTaxLine)
            .filter_by(company_id=self.co.id, source_document_id=51)
            .one()
        )
        self.assertIsNone(line.taxable_base_reporting_currency)
        self.assertIsNone(line.tax_amount_reporting_currency)
        self.assertIsNone(line.exchange_rate)
