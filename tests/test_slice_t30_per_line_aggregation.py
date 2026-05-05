"""Slice T30 tests — DGI L17 … L47 line bucketing.

Validates that ``TaxReturnService._compute_vat_form_lines`` buckets
posted VAT facts into the correct DGI statutory line codes by
inspecting the source ``TaxCode``'s ``return_box_code`` /
``exemption_kind`` / ``is_export`` / ``is_imported_service`` flags.

The test matrix exercises one tax-code variant per intended L-code:

* L17 — standard-rate domestic sales
* L21 — exports (``is_export=True``)
* L22 — exempt sales (``exemption_kind='EXEMPT'``)
* L26 — local goods purchases
* L27 — local services purchases (``return_box_code='L27'``)
* L29 — imported services (``is_imported_service=True``)
* Computed totals L23 / L30 / L36 / L37 / L40 / L43 / L47 follow the
  DGI form formulas.
* Non-recoverable input VAT lands in the informational
  ``L31_NON_DEDUCTIBLE`` bucket — *not* L30.
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
    VAT_EXEMPTION_KIND_EXEMPT,
    VAT_RETURN_LINE_L17,
    VAT_RETURN_LINE_L21,
    VAT_RETURN_LINE_L22,
    VAT_RETURN_LINE_L23,
    VAT_RETURN_LINE_L26,
    VAT_RETURN_LINE_L27,
    VAT_RETURN_LINE_L29,
    VAT_RETURN_LINE_L30,
    VAT_RETURN_LINE_L36,
    VAT_RETURN_LINE_L37,
    VAT_RETURN_LINE_L40,
    VAT_RETURN_LINE_L43,
    VAT_RETURN_LINE_L47,
    VAT_RETURN_LINE_NON_DEDUCTIBLE,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    DraftVATReturnCommand,
)
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    DIRECTION_SALES,
    SOURCE_PURCHASE_BILL,
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
from seeker_accounting.modules.taxation.services.vat_return_form_layout import (
    build_vat_form_layout,
)


_ZERO = Decimal("0.00")


# ─── Test doubles ────────────────────────────────────────────────────────


class _FakeUnitOfWork:
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


# ─── Seed helpers ────────────────────────────────────────────────────────


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    return SF()


def _seed_base(session: Session) -> tuple[int, int, int]:
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
    je = JournalEntry(
        company_id=company.id,
        fiscal_period_id=fp.id,
        entry_number="JE-1",
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
    return company.id, fp.id, je.id


def _make_tax_code(
    session: Session,
    company_id: int,
    *,
    code: str,
    rate: Decimal | None = Decimal("19.2500"),
    is_recoverable: bool | None = None,
    return_box_code: str | None = None,
    exemption_kind: str | None = None,
    is_export: bool = False,
    is_imported_service: bool = False,
) -> TaxCode:
    tc = TaxCode(
        company_id=company_id,
        code=code,
        name=code,
        tax_type_code=TAX_TYPE_VAT,
        calculation_method_code="STANDARD_RATE" if rate else "EXEMPT",
        rate_percent=rate,
        is_recoverable=is_recoverable,
        return_box_code=return_box_code,
        exemption_kind=exemption_kind,
        is_export=is_export,
        is_imported_service=is_imported_service,
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
    direction: str,
    tax_code_id: int,
    base: Decimal,
    tax: Decimal,
    is_recoverable: bool | None = None,
    src_type: str = SOURCE_SALES_INVOICE,
    src_id: int = 1,
) -> None:
    session.add(
        PostedTaxLine(
            company_id=company_id,
            fiscal_period_id=fp_id,
            direction=direction,
            source_document_type=src_type,
            source_document_id=src_id,
            source_line_id=None,
            journal_entry_id=je_id,
            tax_code_id=tax_code_id,
            taxable_base=base,
            tax_amount=tax,
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


def _line(dto, code: str):
    for line in dto.lines:
        if line.box_code == code:
            return line
    return None


def _amount(dto, code: str) -> Decimal:
    line = _line(dto, code)
    return line.amount if line is not None else _ZERO


def _base_amt(dto, code: str) -> Decimal | None:
    line = _line(dto, code)
    return line.base_amount if line is not None else None


# ─── Tests ───────────────────────────────────────────────────────────────


class DgiLineBucketingTests(unittest.TestCase):
    def test_standard_rate_sales_land_in_l17(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        std = _make_tax_code(
            session, company_id, code="VAT-19.25", return_box_code="L17",
        )
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_SALES,
            tax_code_id=std.id,
            base=Decimal("10000.00"),
            tax=Decimal("1925.00"),
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )
        # L17 carries both base and VAT.
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L17), Decimal("10000.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L17), Decimal("1925.00"))
        # L36 = output VAT total = L17 amount.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L36), Decimal("1925.00"))
        # L23 = total turnover excl. taxes = L17 base.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L23), Decimal("10000.00"))
        # L40 = VAT payable since no input VAT.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L40), Decimal("1925.00"))
        # L47 = total amount payable.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L47), Decimal("1925.00"))
        # L43 = credit c/f is zero.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L43), _ZERO)

    def test_exports_land_in_l21_with_zero_vat(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        export = _make_tax_code(
            session, company_id,
            code="VAT-EXPORT",
            rate=Decimal("0.0000"),
            return_box_code="L21",
            is_export=True,
        )
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_SALES,
            tax_code_id=export.id,
            base=Decimal("50000.00"),
            tax=_ZERO,
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L21), Decimal("50000.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L21), _ZERO)
        # Output VAT total stays zero — exports do not contribute to L36.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L36), _ZERO)
        # L23 includes exports as part of total turnover.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L23), Decimal("50000.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L40), _ZERO)

    def test_exempt_sales_land_in_l22_with_no_vat(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        exempt = _make_tax_code(
            session, company_id,
            code="VAT-EXEMPT",
            rate=None,
            return_box_code="L22",
            exemption_kind=VAT_EXEMPTION_KIND_EXEMPT,
        )
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_SALES,
            tax_code_id=exempt.id,
            base=Decimal("12000.00"),
            tax=_ZERO,
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L22), Decimal("12000.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L22), _ZERO)
        # Exempt turnover does NOT contribute to L23 (which sums L17+L18+L19+L20+L21).
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L23), _ZERO)
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L36), _ZERO)

    def test_local_goods_purchase_lands_in_l26(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        purch = _make_tax_code(
            session, company_id,
            code="VAT-IN-L26",
            return_box_code="L26",
            is_recoverable=True,
        )
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_PURCHASE,
            tax_code_id=purch.id,
            base=Decimal("4000.00"),
            tax=Decimal("770.00"),
            is_recoverable=True,
            src_type=SOURCE_PURCHASE_BILL,
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L26), Decimal("4000.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L26), Decimal("770.00"))
        # L30 = sum of L26-L29 VAT.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L30), Decimal("770.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L37), Decimal("770.00"))
        # No sales => credit position.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L40), _ZERO)
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L43), Decimal("770.00"))

    def test_local_services_purchase_lands_in_l27(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        purch = _make_tax_code(
            session, company_id,
            code="VAT-IN-L27",
            return_box_code="L27",
            is_recoverable=True,
        )
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_PURCHASE,
            tax_code_id=purch.id,
            base=Decimal("2000.00"),
            tax=Decimal("385.00"),
            is_recoverable=True,
            src_type=SOURCE_PURCHASE_BILL,
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L27), Decimal("2000.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L27), Decimal("385.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L26), _ZERO)
        # L30 sums L26+L27+L28+L29.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L30), Decimal("385.00"))

    def test_imported_services_land_in_l29(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        purch = _make_tax_code(
            session, company_id,
            code="VAT-IN-L29",
            is_recoverable=True,
            is_imported_service=True,
        )
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_PURCHASE,
            tax_code_id=purch.id,
            base=Decimal("3000.00"),
            tax=Decimal("577.50"),
            is_recoverable=True,
            src_type=SOURCE_PURCHASE_BILL,
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )
        # is_imported_service short-circuits return_box_code: lands in L29.
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L29), Decimal("3000.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L29), Decimal("577.50"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L30), Decimal("577.50"))

    def test_non_recoverable_input_vat_diverted_to_diagnostic_bucket(self) -> None:
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        nr = _make_tax_code(
            session, company_id,
            code="VAT-IN-NR",
            return_box_code="L26",
            is_recoverable=False,
        )
        _add_fact(
            session,
            company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_PURCHASE,
            tax_code_id=nr.id,
            base=Decimal("1000.00"),
            tax=Decimal("192.50"),
            is_recoverable=False,
            src_type=SOURCE_PURCHASE_BILL,
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )
        # Non-recoverable VAT must NOT pollute L26 / L30 / L37.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L26), _ZERO)
        # L26 row exists structurally but carries zero base.
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L26), _ZERO)
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L30), _ZERO)
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L37), _ZERO)
        # It is tracked separately for diagnostics.
        self.assertEqual(
            _amount(dto, VAT_RETURN_LINE_NON_DEDUCTIBLE), Decimal("192.50")
        )

    def test_full_mixed_return_totals_match_dgi_formulas(self) -> None:
        """End-to-end variant matrix — exercises L17 + L21 + L22 + L26 +
        L29 in one return and asserts the computed totals follow the
        DGI formulas (L23, L30, L36, L37, L40/L43, L47).
        """
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        std = _make_tax_code(session, company_id, code="VAT-19.25", return_box_code="L17")
        export = _make_tax_code(
            session, company_id, code="VAT-EXP",
            rate=Decimal("0.0000"), return_box_code="L21", is_export=True,
        )
        exempt = _make_tax_code(
            session, company_id, code="VAT-EX",
            rate=None, return_box_code="L22",
            exemption_kind=VAT_EXEMPTION_KIND_EXEMPT,
        )
        local_goods = _make_tax_code(
            session, company_id, code="VAT-IN-L26",
            return_box_code="L26", is_recoverable=True,
        )
        imp_svc = _make_tax_code(
            session, company_id, code="VAT-IN-IMP",
            is_recoverable=True, is_imported_service=True,
        )

        # Sales mix.
        _add_fact(
            session, company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_SALES, tax_code_id=std.id,
            base=Decimal("10000.00"), tax=Decimal("1925.00"),
        )
        _add_fact(
            session, company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_SALES, tax_code_id=export.id,
            base=Decimal("3000.00"), tax=_ZERO,
            src_id=2,
        )
        _add_fact(
            session, company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_SALES, tax_code_id=exempt.id,
            base=Decimal("2000.00"), tax=_ZERO,
            src_id=3,
        )
        # Purchases.
        _add_fact(
            session, company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_PURCHASE, tax_code_id=local_goods.id,
            base=Decimal("4000.00"), tax=Decimal("770.00"),
            is_recoverable=True, src_type=SOURCE_PURCHASE_BILL, src_id=10,
        )
        _add_fact(
            session, company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_PURCHASE, tax_code_id=imp_svc.id,
            base=Decimal("1000.00"), tax=Decimal("192.50"),
            is_recoverable=True, src_type=SOURCE_PURCHASE_BILL, src_id=11,
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )

        # Sales side
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L17), Decimal("10000.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L17), Decimal("1925.00"))
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L21), Decimal("3000.00"))
        self.assertEqual(_base_amt(dto, VAT_RETURN_LINE_L22), Decimal("2000.00"))
        # L23 = L17+L18+L19+L20+L21 = 10000+0+0+0+3000 = 13000 (exempt L22 excluded).
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L23), Decimal("13000.00"))
        # L36 = sum of output VAT on L17..L20 = 1925.
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L36), Decimal("1925.00"))
        # Purchases side
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L26), Decimal("770.00"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L29), Decimal("192.50"))
        # L30 = L26+L27+L28+L29 VAT
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L30), Decimal("962.50"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L37), Decimal("962.50"))
        # L40 = max(L36 - L37, 0) = 1925 - 962.5 = 962.5
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L40), Decimal("962.50"))
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L43), _ZERO)
        # L47 = L40 (T33 will fold L46 in)
        self.assertEqual(_amount(dto, VAT_RETURN_LINE_L47), Decimal("962.50"))

    def test_form_layout_renders_l_codes(self) -> None:
        """The form-layout read model must read L-codes directly,
        without going through the legacy bridge, for T30-shaped returns.
        """
        session = _make_session()
        company_id, fp_id, je_id = _seed_base(session)
        std = _make_tax_code(session, company_id, code="VAT-19.25", return_box_code="L17")
        _add_fact(
            session, company_id=company_id, fp_id=fp_id, je_id=je_id,
            direction=DIRECTION_SALES, tax_code_id=std.id,
            base=Decimal("10000.00"), tax=Decimal("1925.00"),
        )
        session.flush()
        ob = _seed_obligation(session, company_id)
        dto = _build_service(session).draft_vat_return(
            company_id, DraftVATReturnCommand(obligation_id=ob.id)
        )
        layout = build_vat_form_layout(dto)
        # L17 row carries 10000 base + 1925 amount in section 4.
        section4 = layout.sections[0]
        l17 = next(r for r in section4.rows if r.code == "L17")
        self.assertEqual(l17.base, Decimal("10000.00"))
        self.assertEqual(l17.amount, Decimal("1925.00"))
        # L23 sum row reflects 10000 turnover.
        l23 = next(r for r in section4.rows if r.code == "L23")
        self.assertEqual(l23.base, Decimal("10000.00"))
        # No legacy / unmapped data.
        self.assertFalse(layout.has_unmapped_data)


if __name__ == "__main__":
    unittest.main()
