"""Slice T15 tests — VAT settlement journal entry.

Validates four key areas:

1. **Validation gates** — wrong tax type, non-FILED status, already
   settled, missing return.  Driven via mocks for speed.
2. **Preview aggregation** — exercises the planning code against a
   real in-memory SQLite session with seeded posted_tax_lines and
   tax_code_account_mappings, covering: payable plug, credit
   carry-forward plug, recoverable / non-recoverable input filter,
   missing mapping → blocking issues, missing 4441 / 4449 → blocking
   issues.
3. **Posting** — settle_return creates a balanced POSTED journal
   entry, stamps ``tax_returns.journal_entry_id`` and ``settled_at``,
   and rejects double-settlement with ``ConflictError``.
4. **Period guard** — settling into a LOCKED fiscal period raises
   ``PeriodLockedError``.
"""
from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db import model_registry  # noqa: F401  -- model registration

from seeker_accounting.db.base import Base
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import (
    Account,
)
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
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
from seeker_accounting.modules.accounting.journals.models.journal_entry_line import (
    JournalEntryLine,
)
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.accounting.reference_data.models.account_class import (
    AccountClass,
)
from seeker_accounting.modules.accounting.reference_data.models.account_type import (
    AccountType,
)
from seeker_accounting.modules.accounting.reference_data.models.tax_code import TaxCode
from seeker_accounting.modules.accounting.reference_data.models.tax_code_account_mapping import (
    TaxCodeAccountMapping,
)
from seeker_accounting.modules.accounting.reference_data.repositories.tax_code_account_mapping_repository import (
    TaxCodeAccountMappingRepository,
)
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_FILED,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    SettleTaxReturnCommand,
)
from seeker_accounting.modules.taxation.models.posted_tax_line import (
    DIRECTION_PURCHASE,
    DIRECTION_SALES,
    SOURCE_PURCHASE_BILL,
    SOURCE_SALES_INVOICE,
    PostedTaxLine,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
from seeker_accounting.modules.taxation.repositories.posted_tax_line_repository import (
    PostedTaxLineRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.modules.taxation.services.tax_settlement_service import (
    TaxSettlementService,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PeriodLockedError,
    PermissionDeniedError,
    ValidationError,
)


_ZERO = Decimal("0.00")


# ─── Test scaffolding ───────────────────────────────────────────────────


class _FakeUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.committed = False

    def __enter__(self) -> "_FakeUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        self.session.flush()
        self.session.commit()
        self.committed = True


class _FakePermissionService:
    def __init__(self, granted: set[str]) -> None:
        self._granted = granted

    def require_permission(self, code: str) -> None:
        if code not in self._granted:
            raise PermissionDeniedError(f"Missing permission: {code}")


class _StubNumberingService:
    """Issues sequential ``JE-0001``, ``JE-0002``... numbers."""

    def __init__(self) -> None:
        self._counter = 0

    def issue_next_number(
        self, session: Session, company_id: int, document_type_code: str
    ) -> str:
        self._counter += 1
        return f"JE-{self._counter:04d}"


# ─── Mock-based validation tests ────────────────────────────────────────


def _build_validation_service(
    *,
    granted: set[str] | None = None,
    return_obj: TaxReturn | None = None,
    company_exists: bool = True,
) -> TaxSettlementService:
    if granted is None:
        granted = {TaxSettlementService.PERMISSION_SETTLE}

    session = MagicMock(name="Session")

    return_repo = MagicMock(name="TaxReturnRepository")
    return_repo.get_by_id.return_value = return_obj

    company_repo = MagicMock(name="CompanyRepository")
    company_repo.get_by_id.return_value = (
        SimpleNamespace(id=1) if company_exists else None
    )

    uow = _FakeUnitOfWork(session)

    return TaxSettlementService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        tax_return_repository_factory=lambda s: return_repo,
        posted_tax_line_repository_factory=lambda s: MagicMock(),
        tax_code_account_mapping_repository_factory=lambda s: MagicMock(),
        fiscal_period_repository_factory=lambda s: MagicMock(),
        account_repository_factory=lambda s: MagicMock(),
        journal_entry_repository_factory=lambda s: MagicMock(),
        company_repository_factory=lambda s: company_repo,
        numbering_service=_StubNumberingService(),
        permission_service=_FakePermissionService(granted),
        audit_service=None,
    )


def _make_filed_return(**overrides) -> TaxReturn:
    defaults = dict(
        id=10,
        company_id=1,
        obligation_id=1,
        tax_type_code=TAX_TYPE_VAT,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        status_code=RETURN_STATUS_FILED,
        total_due_amount=_ZERO,
        total_paid_amount=_ZERO,
        journal_entry_id=None,
    )
    defaults.update(overrides)
    return TaxReturn(**defaults)


class SettlementValidationTests(unittest.TestCase):
    def test_missing_permission_rejected(self) -> None:
        service = _build_validation_service(granted=set())
        with self.assertRaises(PermissionDeniedError):
            service.preview_settlement(1, 10)

    def test_missing_company_rejected(self) -> None:
        service = _build_validation_service(company_exists=False)
        with self.assertRaises(NotFoundError):
            service.preview_settlement(1, 10)

    def test_missing_return_rejected(self) -> None:
        service = _build_validation_service(return_obj=None)
        with self.assertRaises(NotFoundError):
            service.preview_settlement(1, 10)

    def test_non_vat_return_rejected(self) -> None:
        rt = _make_filed_return(tax_type_code="CIT_INSTALLMENT")
        service = _build_validation_service(return_obj=rt)
        with self.assertRaises(ValidationError):
            service.preview_settlement(1, 10)

    def test_draft_return_rejected(self) -> None:
        rt = _make_filed_return(status_code=RETURN_STATUS_DRAFT)
        service = _build_validation_service(return_obj=rt)
        with self.assertRaises(ValidationError):
            service.preview_settlement(1, 10)

    def test_already_settled_rejected(self) -> None:
        rt = _make_filed_return(journal_entry_id=999)
        service = _build_validation_service(return_obj=rt)
        with self.assertRaises(ConflictError):
            service.preview_settlement(1, 10)


# ─── Integration tests over an in-memory DB ─────────────────────────────


def _make_session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )


def _seed_chart_minimum(session: Session, *, include_payable: bool = True,
                        include_credit_carryforward: bool = True) -> dict[str, Account]:
    """Seed a minimum company + chart skeleton for VAT settlement.

    Returns a dict mapping account_code → ``Account`` for any account
    callers need to reference (output VAT 4431, input VAT 4451,
    payable 4441, credit-c/f 4449, plus dummy revenue/expense lines).
    """
    company = Company(
        legal_name="Test Co",
        display_name="Test",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()

    cls_passive = AccountClass(code="4", name="Tiers", display_order=4)
    session.add(cls_passive)

    type_liab = AccountType(
        code="LIABILITY",
        name="Liability",
        normal_balance="CREDIT",
        financial_statement_section_code="LIAB",
    )
    type_asset = AccountType(
        code="ASSET",
        name="Asset",
        normal_balance="DEBIT",
        financial_statement_section_code="ASSET",
    )
    session.add_all([type_liab, type_asset])
    session.flush()

    accounts: dict[str, Account] = {}

    def add(code: str, name: str, normal: str, type_id: int) -> Account:
        a = Account(
            company_id=company.id,
            account_code=code,
            account_name=name,
            account_class_id=cls_passive.id,
            account_type_id=type_id,
            normal_balance=normal,
            allow_manual_posting=True,
            is_control_account=False,
        )
        session.add(a)
        accounts[code] = a
        return a

    add("4431", "TVA facturée", "CREDIT", type_liab.id)
    add("4451", "TVA récupérable / Achats", "DEBIT", type_asset.id)
    if include_payable:
        add("4441", "État, TVA due", "CREDIT", type_liab.id)
    if include_credit_carryforward:
        add("4449", "Crédit de TVA à reporter", "DEBIT", type_asset.id)
    session.flush()

    # Set company id on the accounts dict for convenience
    accounts["__company_id__"] = company.id  # type: ignore[assignment]
    return accounts


def _seed_period_and_return(session: Session, company_id: int) -> tuple[FiscalPeriod, TaxReturn]:
    fy = FiscalYear(
        company_id=company_id,
        year_code="FY2026",
        year_name="FY2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status_code="OPEN",
    )
    session.add(fy)
    session.flush()
    fp = FiscalPeriod(
        company_id=company_id,
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
    rt = TaxReturn(
        company_id=company_id,
        obligation_id=ob.id,
        tax_type_code=TAX_TYPE_VAT,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        status_code=RETURN_STATUS_FILED,
        total_due_amount=_ZERO,
        total_paid_amount=_ZERO,
    )
    session.add(rt)
    session.flush()
    return fp, rt


def _seed_tax_codes(session: Session, company_id: int) -> tuple[TaxCode, TaxCode, TaxCode]:
    vat_out = TaxCode(
        company_id=company_id,
        code="VAT-19.25",
        name="VAT 19.25%",
        tax_type_code=TAX_TYPE_VAT,
        calculation_method_code="STANDARD_RATE",
        rate_percent=Decimal("19.2500"),
        is_recoverable=None,
        effective_from=date(2026, 1, 1),
    )
    vat_in_recoverable = TaxCode(
        company_id=company_id,
        code="VAT-IN-19.25",
        name="VAT 19.25% recoverable input",
        tax_type_code=TAX_TYPE_VAT,
        calculation_method_code="STANDARD_RATE",
        rate_percent=Decimal("19.2500"),
        is_recoverable=True,
        effective_from=date(2026, 1, 1),
    )
    vat_in_non_recoverable = TaxCode(
        company_id=company_id,
        code="VAT-IN-NR",
        name="VAT non-recoverable",
        tax_type_code=TAX_TYPE_VAT,
        calculation_method_code="STANDARD_RATE",
        rate_percent=Decimal("19.2500"),
        is_recoverable=False,
        effective_from=date(2026, 1, 1),
    )
    session.add_all([vat_out, vat_in_recoverable, vat_in_non_recoverable])
    session.flush()
    return vat_out, vat_in_recoverable, vat_in_non_recoverable


def _seed_mappings(
    session: Session,
    company_id: int,
    output_tc: TaxCode,
    input_tc: TaxCode,
    nr_tc: TaxCode | None,
    accounts: dict[str, Account],
) -> None:
    session.add(
        TaxCodeAccountMapping(
            company_id=company_id,
            tax_code_id=output_tc.id,
            tax_liability_account_id=accounts["4431"].id,
        )
    )
    session.add(
        TaxCodeAccountMapping(
            company_id=company_id,
            tax_code_id=input_tc.id,
            tax_asset_account_id=accounts["4451"].id,
        )
    )
    if nr_tc is not None:
        # Even non-recoverable tax codes may carry a mapping; the
        # service must still skip their lines.
        session.add(
            TaxCodeAccountMapping(
                company_id=company_id,
                tax_code_id=nr_tc.id,
                tax_asset_account_id=accounts["4451"].id,
            )
        )
    session.flush()


def _seed_anchor_je(session: Session, company_id: int, fp_id: int) -> int:
    je = JournalEntry(
        company_id=company_id,
        fiscal_period_id=fp_id,
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
    return je.id


def _add_posted_tax_line(
    session: Session,
    *,
    company_id: int,
    fp_id: int,
    je_id: int,
    direction: str,
    source_type: str,
    source_id: int,
    tax_code_id: int,
    tax_amount: Decimal,
    is_recoverable: bool | None = None,
    taxable_base: Decimal | None = None,
) -> None:
    if taxable_base is None:
        taxable_base = (tax_amount * Decimal("100") / Decimal("19.25")).quantize(
            Decimal("0.01")
        )
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


def _build_settlement_service(session: Session) -> TaxSettlementService:
    uow = _FakeUnitOfWork(session)
    return TaxSettlementService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        tax_return_repository_factory=TaxReturnRepository,
        posted_tax_line_repository_factory=PostedTaxLineRepository,
        tax_code_account_mapping_repository_factory=TaxCodeAccountMappingRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        account_repository_factory=AccountRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        company_repository_factory=CompanyRepository,
        numbering_service=_StubNumberingService(),
        permission_service=_FakePermissionService(
            {TaxSettlementService.PERMISSION_SETTLE}
        ),
        audit_service=None,
    )


class SettlementPreviewTests(unittest.TestCase):
    def test_payable_plug_when_output_exceeds_input(self) -> None:
        session = _make_session_factory()()
        accounts = _seed_chart_minimum(session)
        company_id = accounts["__company_id__"]  # type: ignore[assignment]
        fp, rt = _seed_period_and_return(session, company_id)
        out_tc, in_tc, _ = _seed_tax_codes(session, company_id)
        _seed_mappings(session, company_id, out_tc, in_tc, None, accounts)
        je_id = _seed_anchor_je(session, company_id, fp.id)
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            tax_amount=Decimal("1925.00"),
        )
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_PURCHASE,
            source_type=SOURCE_PURCHASE_BILL,
            source_id=2,
            tax_code_id=in_tc.id,
            tax_amount=Decimal("500.00"),
            is_recoverable=True,
        )
        session.commit()

        service = _build_settlement_service(session)
        preview = service.preview_settlement(company_id, rt.id)

        self.assertEqual(preview.total_output_vat, Decimal("1925.00"))
        self.assertEqual(preview.total_input_vat_recoverable, Decimal("500.00"))
        self.assertEqual(preview.net_payable_amount, Decimal("1425.00"))
        self.assertEqual(preview.net_credit_carryforward_amount, _ZERO)
        self.assertEqual(preview.blocking_issues, ())

        # Three lines: Dr 4431, Cr 4451, Cr 4441
        roles = {ln.role for ln in preview.journal_lines}
        self.assertEqual(
            roles, {"OUTPUT_VAT", "INPUT_VAT", "VAT_PAYABLE"}
        )
        # Balance check
        total_dr = sum(ln.debit_amount for ln in preview.journal_lines)
        total_cr = sum(ln.credit_amount for ln in preview.journal_lines)
        self.assertEqual(total_dr, total_cr)

    def test_credit_carryforward_when_input_exceeds_output(self) -> None:
        session = _make_session_factory()()
        accounts = _seed_chart_minimum(session)
        company_id = accounts["__company_id__"]  # type: ignore[assignment]
        fp, rt = _seed_period_and_return(session, company_id)
        out_tc, in_tc, _ = _seed_tax_codes(session, company_id)
        _seed_mappings(session, company_id, out_tc, in_tc, None, accounts)
        je_id = _seed_anchor_je(session, company_id, fp.id)
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            tax_amount=Decimal("100.00"),
        )
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_PURCHASE,
            source_type=SOURCE_PURCHASE_BILL,
            source_id=2,
            tax_code_id=in_tc.id,
            tax_amount=Decimal("700.00"),
            is_recoverable=True,
        )
        session.commit()

        service = _build_settlement_service(session)
        preview = service.preview_settlement(company_id, rt.id)

        self.assertEqual(preview.net_payable_amount, _ZERO)
        self.assertEqual(preview.net_credit_carryforward_amount, Decimal("600.00"))
        roles = {ln.role for ln in preview.journal_lines}
        self.assertEqual(
            roles, {"OUTPUT_VAT", "INPUT_VAT", "VAT_CREDIT_CARRYFORWARD"}
        )

    def test_non_recoverable_input_excluded(self) -> None:
        session = _make_session_factory()()
        accounts = _seed_chart_minimum(session)
        company_id = accounts["__company_id__"]  # type: ignore[assignment]
        fp, rt = _seed_period_and_return(session, company_id)
        out_tc, in_tc, nr_tc = _seed_tax_codes(session, company_id)
        _seed_mappings(session, company_id, out_tc, in_tc, nr_tc, accounts)
        je_id = _seed_anchor_je(session, company_id, fp.id)
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            tax_amount=Decimal("1000.00"),
        )
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_PURCHASE,
            source_type=SOURCE_PURCHASE_BILL,
            source_id=2,
            tax_code_id=nr_tc.id,
            tax_amount=Decimal("999.00"),
            is_recoverable=False,
        )
        session.commit()

        service = _build_settlement_service(session)
        preview = service.preview_settlement(company_id, rt.id)
        self.assertEqual(preview.total_input_vat_recoverable, _ZERO)
        self.assertEqual(preview.net_payable_amount, Decimal("1000.00"))

    def test_missing_payable_account_blocks_settlement(self) -> None:
        session = _make_session_factory()()
        accounts = _seed_chart_minimum(session, include_payable=False)
        company_id = accounts["__company_id__"]  # type: ignore[assignment]
        fp, rt = _seed_period_and_return(session, company_id)
        out_tc, in_tc, _ = _seed_tax_codes(session, company_id)
        _seed_mappings(session, company_id, out_tc, in_tc, None, accounts)
        je_id = _seed_anchor_je(session, company_id, fp.id)
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            tax_amount=Decimal("100.00"),
        )
        session.commit()

        service = _build_settlement_service(session)
        preview = service.preview_settlement(company_id, rt.id)
        self.assertTrue(preview.blocking_issues)
        self.assertTrue(
            any("4441" in issue for issue in preview.blocking_issues)
        )

    def test_missing_tax_code_mapping_blocks_settlement(self) -> None:
        session = _make_session_factory()()
        accounts = _seed_chart_minimum(session)
        company_id = accounts["__company_id__"]  # type: ignore[assignment]
        fp, rt = _seed_period_and_return(session, company_id)
        out_tc, _, _ = _seed_tax_codes(session, company_id)
        # Deliberately skip seeding any mappings.
        je_id = _seed_anchor_je(session, company_id, fp.id)
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            tax_amount=Decimal("100.00"),
        )
        session.commit()

        service = _build_settlement_service(session)
        preview = service.preview_settlement(company_id, rt.id)
        self.assertTrue(
            any("mapping" in issue for issue in preview.blocking_issues)
        )


class SettlementPostTests(unittest.TestCase):
    def _setup(
        self,
        *,
        period_status: str = "OPEN",
    ) -> tuple[Session, TaxReturn, int, TaxSettlementService]:
        session = _make_session_factory()()
        accounts = _seed_chart_minimum(session)
        company_id = accounts["__company_id__"]  # type: ignore[assignment]
        fp, rt = _seed_period_and_return(session, company_id)
        if period_status != "OPEN":
            fp.status_code = period_status
            session.flush()
        out_tc, in_tc, _ = _seed_tax_codes(session, company_id)
        _seed_mappings(session, company_id, out_tc, in_tc, None, accounts)
        je_id = _seed_anchor_je(session, company_id, fp.id)
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_SALES,
            source_type=SOURCE_SALES_INVOICE,
            source_id=1,
            tax_code_id=out_tc.id,
            tax_amount=Decimal("1925.00"),
        )
        _add_posted_tax_line(
            session,
            company_id=company_id,
            fp_id=fp.id,
            je_id=je_id,
            direction=DIRECTION_PURCHASE,
            source_type=SOURCE_PURCHASE_BILL,
            source_id=2,
            tax_code_id=in_tc.id,
            tax_amount=Decimal("500.00"),
            is_recoverable=True,
        )
        session.commit()
        service = _build_settlement_service(session)
        return session, rt, company_id, service

    def test_post_creates_balanced_journal_and_links_return(self) -> None:
        session, rt, company_id, service = self._setup()
        result = service.settle_return(
            company_id,
            SettleTaxReturnCommand(return_id=rt.id),
        )
        self.assertIsNotNone(result.journal_entry_id)
        self.assertEqual(result.net_payable_amount, Decimal("1425.00"))

        # Reload return.
        session.expire_all()
        rt = session.get(TaxReturn, rt.id)
        self.assertEqual(rt.journal_entry_id, result.journal_entry_id)
        self.assertIsNotNone(rt.settled_at)

        # Reload JE + lines and check balance + status.
        je = session.get(JournalEntry, result.journal_entry_id)
        self.assertEqual(je.status_code, "POSTED")
        self.assertEqual(je.source_document_type, "tax_return")
        self.assertEqual(je.source_document_id, rt.id)

        from sqlalchemy import select
        lines = list(
            session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == je.id
                )
            )
        )
        self.assertGreaterEqual(len(lines), 3)
        total_dr = sum(l.debit_amount for l in lines)
        total_cr = sum(l.credit_amount for l in lines)
        self.assertEqual(total_dr, total_cr)
        self.assertEqual(total_dr, Decimal("1925.00"))

    def test_double_settle_rejected(self) -> None:
        session, rt, company_id, service = self._setup()
        service.settle_return(
            company_id, SettleTaxReturnCommand(return_id=rt.id)
        )
        # Build a fresh service over the same session — second call
        # must reject the now-settled return.
        service2 = _build_settlement_service(session)
        with self.assertRaises(ConflictError):
            service2.settle_return(
                company_id, SettleTaxReturnCommand(return_id=rt.id)
            )

    def test_locked_period_blocks_post(self) -> None:
        session, rt, company_id, service = self._setup(period_status="LOCKED")
        with self.assertRaises(PeriodLockedError):
            service.settle_return(
                company_id, SettleTaxReturnCommand(return_id=rt.id)
            )


if __name__ == "__main__":
    unittest.main()
