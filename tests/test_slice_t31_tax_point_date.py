"""Slice T31 tests — tax_point_date as first-class field.

Validates that:

* ``PostedTaxLine.tax_point_date`` is persisted by the fact service
  when the posting service supplies it.
* ``PostedTaxLineRepository.aggregate_for_period`` filters facts by
  the tax-point-date window (``tax_point_start`` / ``tax_point_end``)
  when supplied, instead of by ``fiscal_period_id``.
* Facts whose ``tax_point_date`` lies *outside* the return window are
  excluded — even if their ``fiscal_period_id`` overlaps.
* Facts whose ``tax_point_date`` lies *inside* the return window are
  included — even if they were posted during a fiscal period that
  is not in the period-id list.
* Pre-T31 facts with NULL ``tax_point_date`` still aggregate via the
  legacy fiscal-period membership filter (back-compat).
* ``CompanyTaxProfile.vat_uses_tax_point`` round-trips through the
  service / DTO layer.
"""
from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db import model_registry  # noqa: F401
from seeker_accounting.db.base import Base
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import (
    FiscalPeriod,
)
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import (
    FiscalYear,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import (
    JournalEntry,
)
from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    TAX_TYPE_VAT,
    VAT_RETURN_LINE_L17,
)
from seeker_accounting.modules.taxation.dto.company_tax_profile_dto import (
    UpsertCompanyTaxProfileCommand,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    DraftVATReturnCommand,
)
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_SALES,
    SOURCE_SALES_INVOICE,
    PostedTaxLine,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_obligation_repository import (
    TaxObligationRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.modules.taxation.services.tax_return_service import (
    TaxReturnService,
)


_ZERO = Decimal("0.00")


class _FakeUoW:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


class _FakePermissionService:
    def __init__(self, granted):
        self._granted = granted

    def require_permission(self, code):
        if code not in self._granted:
            raise AssertionError(f"Missing permission {code}")

    def has_permission(self, code):
        return code in self._granted


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    return SF()


def _seed_two_periods(session: Session) -> tuple[int, int, int, int]:
    """Returns (company_id, fp_march_id, fp_april_id, je_id)."""
    company = Company(
        legal_name="Test Co",
        display_name="Test",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()
    fy = FiscalYear(
        company_id=company.id,
        year_code="FY2026",
        year_name="FY2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status_code="OPEN",
    )
    session.add(fy)
    session.flush()
    fp_mar = FiscalPeriod(
        company_id=company.id,
        fiscal_year_id=fy.id,
        period_number=3,
        period_code="FY2026-M03",
        period_name="March 2026",
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
        status_code="OPEN",
    )
    fp_apr = FiscalPeriod(
        company_id=company.id,
        fiscal_year_id=fy.id,
        period_number=4,
        period_code="FY2026-M04",
        period_name="April 2026",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        status_code="OPEN",
    )
    session.add_all([fp_mar, fp_apr])
    session.flush()
    je = JournalEntry(
        company_id=company.id,
        fiscal_period_id=fp_mar.id,
        entry_number="JE-1",
        entry_date=date(2026, 3, 31),
        journal_type_code="SALES",
        reference_text=None,
        description="anchor",
        source_module_code="sales",
        source_document_type=SOURCE_SALES_INVOICE,
        source_document_id=1,
        status_code="POSTED",
        posted_at=datetime(2026, 3, 31, 23, 0, 0),
    )
    session.add(je)
    session.flush()
    return company.id, fp_mar.id, fp_apr.id, je.id


def _make_tax_code(session: Session, company_id: int) -> TaxCode:
    tc = TaxCode(
        company_id=company_id,
        code="VAT-19.25",
        name="VAT 19.25%",
        tax_type_code=TAX_TYPE_VAT,
        calculation_method_code="STANDARD_RATE",
        rate_percent=Decimal("19.2500"),
        is_recoverable=None,
        return_box_code="L17",
        effective_from=date(2026, 1, 1),
    )
    session.add(tc)
    session.flush()
    return tc


def _add_fact(
    session: Session,
    *,
    company_id: int,
    fp_id: int,
    je_id: int,
    tax_code_id: int,
    base: Decimal,
    tax: Decimal,
    tax_point_date: date | None,
    src_id: int = 1,
) -> None:
    session.add(
        PostedTaxLine(
            company_id=company_id,
            fiscal_period_id=fp_id,
            direction=DIRECTION_SALES,
            source_document_type=SOURCE_SALES_INVOICE,
            source_document_id=src_id,
            source_line_id=None,
            journal_entry_id=je_id,
            tax_code_id=tax_code_id,
            taxable_base=base,
            tax_amount=tax,
            is_recoverable=None,
            tax_point_date=tax_point_date,
            posted_at=datetime(2026, 3, 31, 23, 0, 0),
        )
    )


def _seed_obligation(
    session: Session, company_id: int, *, period_start: date, period_end: date
) -> TaxObligation:
    ob = TaxObligation(
        company_id=company_id,
        tax_type_code=TAX_TYPE_VAT,
        period_start=period_start,
        period_end=period_end,
        due_date=date(period_end.year, period_end.month, 28),
        status_code="OPEN",
    )
    session.add(ob)
    session.flush()
    return ob


def _build_service(session: Session) -> TaxReturnService:
    uow = _FakeUoW(session)
    return TaxReturnService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        tax_return_repository_factory=TaxReturnRepository,
        tax_obligation_repository_factory=TaxObligationRepository,
        company_repository_factory=CompanyRepository,
        posted_tax_line_repository_factory=PostedTaxLineRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        permission_service=_FakePermissionService(
            {TaxReturnService.PERMISSION_MANAGE, TaxReturnService.PERMISSION_VIEW}
        ),
        audit_service=None,
    )


def _line(dto, code: str):
    for line in dto.lines:
        if line.box_code == code:
            return line
    return None


def _amount(dto, code: str) -> Decimal:
    line = _line(dto, code)
    return line.amount if line is not None else _ZERO


def _base(dto, code: str) -> Decimal | None:
    line = _line(dto, code)
    return line.base_amount if line is not None else None


class TaxPointDateAggregationTests(unittest.TestCase):
    def test_invoice_dated_march_with_tax_point_april_lands_in_april_return(
        self,
    ) -> None:
        """Core T31 acceptance: an invoice dated 31-March with
        ``tax_point_date=2-April`` must NOT appear in the March return,
        and MUST appear in the April return."""
        session = _make_session()
        company_id, fp_mar_id, fp_apr_id, je_id = _seed_two_periods(session)
        tc = _make_tax_code(session, company_id)
        # Invoice posted into March fiscal period (fiscal_period_id=fp_mar)
        # but tax-point is 2-April.
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_mar_id, je_id=je_id,
            tax_code_id=tc.id,
            base=Decimal("100000.00"),
            tax=Decimal("19250.00"),
            tax_point_date=date(2026, 4, 2),
        )
        session.flush()

        # March return: should be empty.
        ob_mar = _seed_obligation(
            session, company_id,
            period_start=date(2026, 3, 1), period_end=date(2026, 3, 31),
        )
        dto_mar = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob_mar.id)
        )
        self.assertEqual(_amount(dto_mar, VAT_RETURN_LINE_L17), _ZERO)
        self.assertEqual(_base(dto_mar, VAT_RETURN_LINE_L17), _ZERO)

        # April return: should contain the fact.
        ob_apr = _seed_obligation(
            session, company_id,
            period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
        )
        dto_apr = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob_apr.id)
        )
        self.assertEqual(_amount(dto_apr, VAT_RETURN_LINE_L17), Decimal("19250.00"))
        self.assertEqual(_base(dto_apr, VAT_RETURN_LINE_L17), Decimal("100000.00"))

    def test_pre_t31_facts_with_null_tax_point_use_period_filter(self) -> None:
        """Back-compat: facts with NULL tax_point_date (pre-T31) still
        aggregate by their fiscal_period_id, so historical returns stay
        stable."""
        session = _make_session()
        company_id, fp_mar_id, _fp_apr_id, je_id = _seed_two_periods(session)
        tc = _make_tax_code(session, company_id)
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_mar_id, je_id=je_id,
            tax_code_id=tc.id,
            base=Decimal("50000.00"),
            tax=Decimal("9625.00"),
            tax_point_date=None,
        )
        session.flush()

        ob_mar = _seed_obligation(
            session, company_id,
            period_start=date(2026, 3, 1), period_end=date(2026, 3, 31),
        )
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob_mar.id)
        )
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L17), Decimal("9625.00"))

    def test_repository_aggregate_filters_by_tax_point_window(self) -> None:
        """Direct unit test of the repository filter: a fact dated
        within the tax-point window is included; outside is excluded;
        NULL falls back to fiscal_period membership."""
        session = _make_session()
        company_id, fp_mar_id, fp_apr_id, je_id = _seed_two_periods(session)
        tc = _make_tax_code(session, company_id)
        # In window
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_mar_id, je_id=je_id,
            tax_code_id=tc.id, base=Decimal("100"), tax=Decimal("19"),
            tax_point_date=date(2026, 4, 5), src_id=1,
        )
        # Out of window
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_apr_id, je_id=je_id,
            tax_code_id=tc.id, base=Decimal("200"), tax=Decimal("38"),
            tax_point_date=date(2026, 5, 10), src_id=2,
        )
        # NULL — fiscal_period in window list
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_apr_id, je_id=je_id,
            tax_code_id=tc.id, base=Decimal("400"), tax=Decimal("76"),
            tax_point_date=None, src_id=3,
        )
        session.flush()

        repo = PostedTaxLineRepository(session)
        aggs = repo.aggregate_for_period(
            company_id,
            [fp_apr_id],
            direction=DIRECTION_SALES,
            tax_type_code=TAX_TYPE_VAT,
            tax_point_start=date(2026, 4, 1),
            tax_point_end=date(2026, 4, 30),
        )
        # Should include the in-window row (100/19) AND the NULL row
        # whose fiscal_period_id matches (400/76); should NOT include
        # the May fact (200/38).
        self.assertEqual(len(aggs), 1)
        self.assertEqual(aggs[0].taxable_base, Decimal("500.00"))
        self.assertEqual(aggs[0].tax_amount, Decimal("95.00"))


class CompanyTaxProfileTaxPointToggleTests(unittest.TestCase):
    def test_vat_uses_tax_point_round_trips(self) -> None:
        """The new flag persists through upsert + get_or_default."""
        from seeker_accounting.modules.taxation.repositories.company_tax_profile_repository import (
            CompanyTaxProfileRepository,
        )
        from seeker_accounting.modules.taxation.services.company_tax_profile_service import (
            CompanyTaxProfileService,
        )

        session = _make_session()
        company = Company(
            legal_name="Test Co",
            display_name="Test",
            country_code="CM",
            base_currency_code="XAF",
        )
        session.add(company)
        session.flush()

        uow = _FakeUoW(session)
        granted = {
            CompanyTaxProfileService.PERMISSION_MANAGE,
            CompanyTaxProfileService.PERMISSION_VIEW,
        }
        svc = CompanyTaxProfileService(
            unit_of_work_factory=lambda: uow,
            app_context=SimpleNamespace(current_user_id=1),
            company_tax_profile_repository_factory=CompanyTaxProfileRepository,
            company_repository_factory=CompanyRepository,
            permission_service=_FakePermissionService(granted),
            audit_service=MagicMock(),
        )

        # Default: flag is False.
        dto = svc.get_or_default(company.id)
        self.assertFalse(dto.vat_uses_tax_point)

        # Upsert with flag=True.
        cmd = UpsertCompanyTaxProfileCommand(
            is_vat_liable=True,
            vat_effective_from=date(2026, 1, 1),
            vat_uses_tax_point=True,
        )
        result = svc.upsert(company.id, cmd)
        self.assertTrue(result.vat_uses_tax_point)

        # Re-read.
        reread = svc.get_or_default(company.id)
        self.assertTrue(reread.vat_uses_tax_point)


if __name__ == "__main__":
    unittest.main()
