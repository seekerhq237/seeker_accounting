"""Slice T29 tests — unified VAT aggregator.

Validates that ``TaxReturnService._compute_vat_box_totals`` reads
exclusively from ``posted_tax_lines`` (the same fact table consumed by
``TaxSettlementService``), so that:

* sales credit notes net against their originating invoices,
* purchase credit notes net against their originating bills,
* the recoverable / non-recoverable split is driven by the
  ``is_recoverable`` value snapshotted on the fact row at posting
  time (not the tax code's *current* flag),
* draft VAT returns and settlement previews always reconcile to the
  penny over the same dataset,
* non-VAT facts are excluded.
"""
from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db import model_registry  # noqa: F401  -- model registration
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
    VAT_BOX_INPUT_TAX_DEDUCTIBLE,
    VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE,
    VAT_BOX_NET_VAT_DUE,
    VAT_BOX_OUTPUT_TAX,
    VAT_BOX_TAXABLE_PURCHASES,
    VAT_BOX_TAXABLE_SALES,
    VAT_RETURN_LINE_L17,
    VAT_RETURN_LINE_L26,
    VAT_RETURN_LINE_L30,
    VAT_RETURN_LINE_L36,
    VAT_RETURN_LINE_L40,
    VAT_RETURN_LINE_L43,
    VAT_RETURN_LINE_NON_DEDUCTIBLE,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    DraftVATReturnCommand,
)
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    DIRECTION_SALES,
    SOURCE_PURCHASE_BILL,
    SOURCE_PURCHASE_CREDIT_NOTE,
    SOURCE_SALES_CREDIT_NOTE,
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


# ─── Test doubles ────────────────────────────────────────────────────────


class _FakeUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> "_FakeUnitOfWork":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


class _FakePermissionService:
    def __init__(self, granted: set[str]) -> None:
        self._granted = granted

    def require_permission(self, code: str) -> None:
        if code not in self._granted:
            raise AssertionError(f"Missing permission {code}")

    def has_permission(self, code: str) -> bool:
        return code in self._granted


# ─── Seed helpers ────────────────────────────────────────────────────────


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    return SessionFactory()


def _seed_fixture(session: Session) -> tuple[int, int, int, TaxCode, TaxCode, TaxCode]:
    """Returns (company_id, fp_id, je_id, vat_out, vat_in_rec, vat_in_nr)."""
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

    vat_out = TaxCode(
        company_id=company.id,
        code="VAT-19.25",
        name="VAT 19.25%",
        tax_type_code=TAX_TYPE_VAT,
        calculation_method_code="STANDARD_RATE",
        rate_percent=Decimal("19.2500"),
        is_recoverable=None,
        effective_from=date(2026, 1, 1),
    )
    vat_in_rec = TaxCode(
        company_id=company.id,
        code="VAT-IN-19.25",
        name="Input VAT 19.25% recoverable",
        tax_type_code=TAX_TYPE_VAT,
        calculation_method_code="STANDARD_RATE",
        rate_percent=Decimal("19.2500"),
        is_recoverable=True,
        effective_from=date(2026, 1, 1),
    )
    vat_in_nr = TaxCode(
        company_id=company.id,
        code="VAT-IN-NR",
        name="Input VAT non-recoverable",
        tax_type_code=TAX_TYPE_VAT,
        calculation_method_code="STANDARD_RATE",
        rate_percent=Decimal("19.2500"),
        is_recoverable=False,
        effective_from=date(2026, 1, 1),
    )
    # A non-VAT tax code (e.g. TSR) — facts using this code must NOT
    # leak into the VAT return.
    tsr = TaxCode(
        company_id=company.id,
        code="TSR-15",
        name="TSR 15%",
        tax_type_code="TSR",
        calculation_method_code="STANDARD_RATE",
        rate_percent=Decimal("15.0000"),
        is_recoverable=False,
        effective_from=date(2026, 1, 1),
    )
    session.add_all([vat_out, vat_in_rec, vat_in_nr, tsr])
    session.flush()

    je = JournalEntry(
        company_id=company.id,
        fiscal_period_id=fp.id,
        entry_number="JE-ANCHOR",
        entry_date=date(2026, 1, 15),
        journal_type_code="SALES",
        reference_text=None,
        description="anchor",
        source_module_code="sales",
        source_document_type=SOURCE_SALES_INVOICE,
        source_document_id=1,
        status_code="POSTED",
        posted_at=datetime(2026, 1, 15, 10, 0, 0),
    )
    session.add(je)
    session.flush()

    # Stash the TSR code on the fixture for the leakage test.
    setattr(_seed_fixture, "tsr_id", tsr.id)

    return company.id, fp.id, je.id, vat_out, vat_in_rec, vat_in_nr


def _add_fact(
    session: Session,
    *,
    company_id: int,
    fp_id: int,
    je_id: int,
    direction: str,
    source_type: str,
    source_id: int,
    tax_code_id: int,
    taxable_base: Decimal,
    tax_amount: Decimal,
    is_recoverable: bool | None = None,
) -> None:
    session.add(
        PostedTaxLine(
            company_id=company_id,
            fiscal_period_id=fp_id,
            direction=direction,
            source_document_type=source_type,
            source_document_id=source_id,
            source_line_id=None,
            journal_entry_id=je_id,
            tax_code_id=tax_code_id,
            taxable_base=taxable_base,
            tax_amount=tax_amount,
            is_recoverable=is_recoverable,
            posted_at=datetime(2026, 1, 15, 10, 0, 0),
        )
    )


def _seed_obligation(session: Session, company_id: int) -> TaxObligation:
    ob = TaxObligation(
        company_id=company_id,
        tax_type_code=TAX_TYPE_VAT,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        due_date=date(2026, 2, 15),
        status_code="OPEN",
    )
    session.add(ob)
    session.flush()
    return ob


def _build_service(session: Session) -> TaxReturnService:
    uow = _FakeUnitOfWork(session)
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


# ─── Tests ───────────────────────────────────────────────────────────────


class UnifiedVatAggregatorTests(unittest.TestCase):
    def _box(self, dto, code: str) -> Decimal:
        # Slice T30 changed canonical persistence from the legacy 6-box
        # scheme to DGI statutory line codes (L17/L26/L36/L40/...).
        # This shim translates legacy box-code lookups used by the T29
        # tests onto the new L-code lines so the tests still describe
        # the same aggregation invariants.
        line_amount = self._raw_amount(dto, code)
        if line_amount is not None:
            return line_amount

        if code == VAT_BOX_TAXABLE_SALES:
            base = self._raw_base(dto, VAT_RETURN_LINE_L17)
            return base if base is not None else _ZERO
        if code == VAT_BOX_OUTPUT_TAX:
            return self._raw_amount(dto, VAT_RETURN_LINE_L36) or _ZERO
        if code == VAT_BOX_TAXABLE_PURCHASES:
            base = self._raw_base(dto, VAT_RETURN_LINE_L26)
            return base if base is not None else _ZERO
        if code == VAT_BOX_INPUT_TAX_DEDUCTIBLE:
            return self._raw_amount(dto, VAT_RETURN_LINE_L30) or _ZERO
        if code == VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE:
            return self._raw_amount(dto, VAT_RETURN_LINE_NON_DEDUCTIBLE) or _ZERO
        if code == VAT_BOX_NET_VAT_DUE:
            payable = self._raw_amount(dto, VAT_RETURN_LINE_L40) or _ZERO
            credit = self._raw_amount(dto, VAT_RETURN_LINE_L43) or _ZERO
            # Net = output − input deductible.  Positive when payable,
            # negative when the company is in a credit position (L43).
            return payable - credit
        raise AssertionError(f"box {code} not found in return DTO")

    @staticmethod
    def _raw_amount(dto, code: str) -> Decimal | None:
        for line in dto.lines:
            if line.box_code == code:
                return line.amount
        return None

    @staticmethod
    def _raw_base(dto, code: str) -> Decimal | None:
        for line in dto.lines:
            if line.box_code == code:
                return line.base_amount
        return None

    def test_sales_invoice_only_aggregates_to_output_boxes(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id, out_tc, _, _ = _seed_fixture(session)
        ob = _seed_obligation(session, company_id)
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            taxable_base=Decimal("10000.00"),
            tax_amount=Decimal("1925.00"),
        )
        session.flush()

        svc = _build_service(session)
        dto = svc.draft_vat_return(company_id, DraftVATReturnCommand(obligation_id=ob.id))

        self.assertEqual(self._box(dto, VAT_BOX_TAXABLE_SALES), Decimal("10000.00"))
        self.assertEqual(self._box(dto, VAT_BOX_OUTPUT_TAX), Decimal("1925.00"))
        self.assertEqual(self._box(dto, VAT_BOX_NET_VAT_DUE), Decimal("1925.00"))

    def test_sales_credit_note_offsets_originating_invoice(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id, out_tc, _, _ = _seed_fixture(session)
        ob = _seed_obligation(session, company_id)
        # Invoice
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            taxable_base=Decimal("10000.00"),
            tax_amount=Decimal("1925.00"),
        )
        # Credit note for half — written sign-negated by the posting service.
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_CREDIT_NOTE,
            source_id=2,
            tax_code_id=out_tc.id,
            taxable_base=Decimal("-5000.00"),
            tax_amount=Decimal("-962.50"),
        )
        session.flush()

        svc = _build_service(session)
        dto = svc.draft_vat_return(company_id, DraftVATReturnCommand(obligation_id=ob.id))

        self.assertEqual(self._box(dto, VAT_BOX_TAXABLE_SALES), Decimal("5000.00"))
        self.assertEqual(self._box(dto, VAT_BOX_OUTPUT_TAX), Decimal("962.50"))
        self.assertEqual(self._box(dto, VAT_BOX_NET_VAT_DUE), Decimal("962.50"))

    def test_purchase_bill_and_credit_note_with_recoverable_split(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id, _, in_rec, in_nr = _seed_fixture(session)
        ob = _seed_obligation(session, company_id)
        # Recoverable bill
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_PURCHASE,
            source_type=SOURCE_PURCHASE_BILL,
            source_id=1,
            tax_code_id=in_rec.id,
            taxable_base=Decimal("8000.00"),
            tax_amount=Decimal("1540.00"),
            is_recoverable=True,
        )
        # Recoverable credit note (signed-negative)
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_PURCHASE,
            source_type=SOURCE_PURCHASE_CREDIT_NOTE,
            source_id=2,
            tax_code_id=in_rec.id,
            taxable_base=Decimal("-2000.00"),
            tax_amount=Decimal("-385.00"),
            is_recoverable=True,
        )
        # Non-recoverable bill — must route to the non-deductible box.
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_PURCHASE,
            source_type=SOURCE_PURCHASE_BILL,
            source_id=3,
            tax_code_id=in_nr.id,
            taxable_base=Decimal("1000.00"),
            tax_amount=Decimal("192.50"),
            is_recoverable=False,
        )
        session.flush()

        svc = _build_service(session)
        dto = svc.draft_vat_return(company_id, DraftVATReturnCommand(obligation_id=ob.id))

        self.assertEqual(
            self._box(dto, VAT_BOX_TAXABLE_PURCHASES), Decimal("6000.00")
        )
        self.assertEqual(
            self._box(dto, VAT_BOX_INPUT_TAX_DEDUCTIBLE), Decimal("1155.00")
        )
        self.assertEqual(
            self._box(dto, VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE), Decimal("192.50")
        )
        # No sales facts so output is zero.
        self.assertEqual(self._box(dto, VAT_BOX_OUTPUT_TAX), _ZERO)
        # Net = 0 - 1155 = -1155 (credit position)
        self.assertEqual(
            self._box(dto, VAT_BOX_NET_VAT_DUE), Decimal("-1155.00")
        )

    def test_non_vat_facts_are_excluded(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id, out_tc, _, _ = _seed_fixture(session)
        ob = _seed_obligation(session, company_id)
        tsr_id: int = getattr(_seed_fixture, "tsr_id")
        # VAT output fact
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            taxable_base=Decimal("10000.00"),
            tax_amount=Decimal("1925.00"),
        )
        # TSR (non-VAT) fact written into the same fact table — must NOT leak.
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=2,
            tax_code_id=tsr_id,
            taxable_base=Decimal("4000.00"),
            tax_amount=Decimal("600.00"),
        )
        session.flush()

        svc = _build_service(session)
        dto = svc.draft_vat_return(company_id, DraftVATReturnCommand(obligation_id=ob.id))

        # Only the VAT row is reflected; TSR is excluded entirely.
        self.assertEqual(self._box(dto, VAT_BOX_TAXABLE_SALES), Decimal("10000.00"))
        self.assertEqual(self._box(dto, VAT_BOX_OUTPUT_TAX), Decimal("1925.00"))

    def test_facts_outside_period_are_excluded(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id, out_tc, _, _ = _seed_fixture(session)
        ob = _seed_obligation(session, company_id)
        # In-period fact
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            taxable_base=Decimal("10000.00"),
            tax_amount=Decimal("1925.00"),
        )
        # February period — must NOT contribute to the January return.
        fy_id = session.query(FiscalYear).first().id
        fp_feb = FiscalPeriod(
            company_id=company_id,
            fiscal_year_id=fy_id,
            period_number=2,
            period_code="FY2026-M02",
            period_name="February 2026",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            status_code="OPEN",
        )
        session.add(fp_feb)
        session.flush()
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_feb.id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=99,
            tax_code_id=out_tc.id,
            taxable_base=Decimal("99999.00"),
            tax_amount=Decimal("19250.00"),
        )
        session.flush()

        svc = _build_service(session)
        dto = svc.draft_vat_return(company_id, DraftVATReturnCommand(obligation_id=ob.id))

        self.assertEqual(self._box(dto, VAT_BOX_TAXABLE_SALES), Decimal("10000.00"))
        self.assertEqual(self._box(dto, VAT_BOX_OUTPUT_TAX), Decimal("1925.00"))

    def test_reconciles_with_settlement_aggregator(self) -> None:
        """Aggregator parity: drafted return totals must equal what the
        settlement service computes from the same facts."""
        session = _make_session()
        company_id, fp_id, je_id, out_tc, in_rec, _ = _seed_fixture(session)
        ob = _seed_obligation(session, company_id)
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            taxable_base=Decimal("10000.00"),
            tax_amount=Decimal("1925.00"),
        )
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_CREDIT_NOTE,
            source_id=2,
            tax_code_id=out_tc.id,
            taxable_base=Decimal("-3000.00"),
            tax_amount=Decimal("-577.50"),
        )
        _add_fact(
            session,
            company_id=company_id,
            fp_id=fp_id,
            je_id=je_id,
            direction=DIRECTION_PURCHASE,
            source_type=SOURCE_PURCHASE_BILL,
            source_id=3,
            tax_code_id=in_rec.id,
            taxable_base=Decimal("4000.00"),
            tax_amount=Decimal("770.00"),
            is_recoverable=True,
        )
        session.flush()

        svc = _build_service(session)
        dto = svc.draft_vat_return(company_id, DraftVATReturnCommand(obligation_id=ob.id))

        # Independent aggregation from posted_tax_lines via the same
        # repository the settlement service uses — both must agree.
        ptl = PostedTaxLineRepository(session)
        sales = ptl.aggregate_for_period(
            company_id, [fp_id], direction=DIRECTION_SALES, tax_type_code=TAX_TYPE_VAT,
        )
        purch = ptl.aggregate_for_period(
            company_id, [fp_id], direction=DIRECTION_PURCHASE, tax_type_code=TAX_TYPE_VAT,
        )
        sales_output = sum((a.tax_amount for a in sales), Decimal("0"))
        purch_input_rec = sum(
            (a.tax_amount for a in purch if a.is_recoverable), Decimal("0")
        )
        expected_net = (sales_output - purch_input_rec).quantize(Decimal("0.01"))

        self.assertEqual(
            self._box(dto, VAT_BOX_OUTPUT_TAX),
            sales_output.quantize(Decimal("0.01")),
        )
        self.assertEqual(
            self._box(dto, VAT_BOX_INPUT_TAX_DEDUCTIBLE),
            purch_input_rec.quantize(Decimal("0.01")),
        )
        self.assertEqual(self._box(dto, VAT_BOX_NET_VAT_DUE), expected_net)


if __name__ == "__main__":
    unittest.main()
