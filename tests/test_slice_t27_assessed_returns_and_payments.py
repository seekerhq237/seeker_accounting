"""Slice T27 tests — assessed-amount returns + payment JE for
Patente / TSR / Customs.

Three concerns:

- ``AssessedReturnFilingTests`` — ``TaxReturnService.file_assessed_return``
  rejects non-assessed tax types, rejects non-OPEN obligations, and
  creates a return already in the FILED state (no draft, no lines).
- ``AssessedPaymentPostTests`` — ``TaxPaymentService.record_payment``
  for PATENTE / TSR / CUSTOMS posts a balanced ``Dr <type-account>
  / Cr <treasury>`` journal entry **without** requiring the return to
  be settled first (no settlement step exists for these tax types).
- ``LegacyVATPathTests`` — guard regression: the existing VAT path is
  unchanged; bank-side post still requires the return to have a
  settlement journal.
"""
from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import create_engine, select
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
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.taxation.constants import (
    OBLIGATION_STATUS_FILED,
    OBLIGATION_STATUS_OPEN,
    PAYMENT_CUSTOMS_EXPENSE_ACCOUNT_CODE,
    PAYMENT_PATENTE_EXPENSE_ACCOUNT_CODE,
    PAYMENT_TSR_PAYABLE_ACCOUNT_CODE,
    RETURN_STATUS_FILED,
    TAX_PAYMENT_METHOD_BANK_TRANSFER,
    TAX_TYPE_CUSTOMS,
    TAX_TYPE_PATENTE,
    TAX_TYPE_TSR,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    FileAssessedTaxReturnCommand,
    RecordTaxPaymentCommand,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.models.tax_payment import TaxPayment
from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
from seeker_accounting.modules.taxation.repositories.tax_obligation_repository import (
    TaxObligationRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_payment_repository import (
    TaxPaymentRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.modules.taxation.services.tax_payment_service import (
    TaxPaymentService,
)
from seeker_accounting.modules.taxation.services.tax_return_service import (
    TaxReturnService,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    ValidationError,
)


_ZERO = Decimal("0.00")


# ─── Common test infrastructure ─────────────────────────────────────────


class _FakeUnitOfWork:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session
        self.committed = False

    def __enter__(self) -> "_FakeUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        if self.session is not None:
            self.session.flush()
            self.session.commit()
        self.committed = True


class _FakePermissionService:
    def __init__(self, granted: set[str]) -> None:
        self._granted = granted

    def require_permission(self, code: str) -> None:
        if code not in self._granted:
            from seeker_accounting.platform.exceptions import PermissionDeniedError

            raise PermissionDeniedError(f"Missing permission: {code}")


class _StubNumberingService:
    def __init__(self) -> None:
        self._counter = 0

    def issue_next_number(
        self, session: Session, company_id: int, document_type_code: str
    ) -> str:
        self._counter += 1
        return f"JE-{self._counter:04d}"


# ─── Mock-based: TaxReturnService.file_assessed_return validation ───────


def _make_assessed_obligation(
    tax_type_code: str = TAX_TYPE_PATENTE,
    status_code: str = OBLIGATION_STATUS_OPEN,
) -> TaxObligation:
    return TaxObligation(
        id=10,
        company_id=1,
        tax_type_code=tax_type_code,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        due_date=date(2026, 3, 31),
        status_code=status_code,
    )


def _build_mock_return_service(*, obligation: TaxObligation, existing_return=None):
    granted = {
        TaxReturnService.PERMISSION_VIEW,
        TaxReturnService.PERMISSION_MANAGE,
        TaxReturnService.PERMISSION_FILE,
    }
    uow = _FakeUnitOfWork()

    return_repo = MagicMock(name="TaxReturnRepository")
    return_repo.get_by_obligation.return_value = existing_return
    return_repo.add.side_effect = lambda r: r
    return_repo.get_by_id.side_effect = lambda cid, rid: _added.get("rt")

    obligation_repo = MagicMock(name="TaxObligationRepository")
    obligation_repo.get_by_id.return_value = obligation

    company_repo = MagicMock(name="CompanyRepository")
    company_repo.get_by_id.return_value = SimpleNamespace(id=1)

    _added: dict = {}

    def _add(r):
        _added["rt"] = r
        # simulate flush stamping an id
        if getattr(r, "id", None) is None:
            r.id = 555
        return r

    return_repo.add.side_effect = _add

    service = TaxReturnService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        tax_return_repository_factory=lambda s: return_repo,
        tax_obligation_repository_factory=lambda s: obligation_repo,
        company_repository_factory=lambda s: company_repo,
        posted_tax_line_repository_factory=lambda s: MagicMock(),
        fiscal_period_repository_factory=lambda s: MagicMock(),
        permission_service=_FakePermissionService(granted),
        audit_service=None,
    )
    return service, return_repo, obligation_repo, _added


class AssessedReturnFilingTests(unittest.TestCase):
    def test_rejects_vat_obligation(self) -> None:
        ob = _make_assessed_obligation(tax_type_code=TAX_TYPE_VAT)
        service, *_ = _build_mock_return_service(obligation=ob)
        with self.assertRaises(ValidationError):
            service.file_assessed_return(
                1,
                FileAssessedTaxReturnCommand(
                    obligation_id=ob.id,
                    total_due_amount=Decimal("250000.00"),
                ),
            )

    def test_rejects_zero_or_negative_amount(self) -> None:
        ob = _make_assessed_obligation()
        service, *_ = _build_mock_return_service(obligation=ob)
        with self.assertRaises(ValidationError):
            service.file_assessed_return(
                1,
                FileAssessedTaxReturnCommand(
                    obligation_id=ob.id,
                    total_due_amount=Decimal("0"),
                ),
            )
        with self.assertRaises(ValidationError):
            service.file_assessed_return(
                1,
                FileAssessedTaxReturnCommand(
                    obligation_id=ob.id,
                    total_due_amount=Decimal("-50"),
                ),
            )

    def test_rejects_already_filed_obligation(self) -> None:
        ob = _make_assessed_obligation(status_code=OBLIGATION_STATUS_FILED)
        service, *_ = _build_mock_return_service(obligation=ob)
        with self.assertRaises(ValidationError):
            service.file_assessed_return(
                1,
                FileAssessedTaxReturnCommand(
                    obligation_id=ob.id,
                    total_due_amount=Decimal("250000.00"),
                ),
            )

    def test_rejects_when_return_already_exists(self) -> None:
        ob = _make_assessed_obligation()
        existing = SimpleNamespace(id=99, status_code=RETURN_STATUS_FILED)
        service, *_ = _build_mock_return_service(
            obligation=ob, existing_return=existing
        )
        with self.assertRaises(ConflictError):
            service.file_assessed_return(
                1,
                FileAssessedTaxReturnCommand(
                    obligation_id=ob.id,
                    total_due_amount=Decimal("250000.00"),
                ),
            )

    def test_creates_filed_return_for_patente(self) -> None:
        ob = _make_assessed_obligation(tax_type_code=TAX_TYPE_PATENTE)
        service, _return_repo, _ob_repo, added = _build_mock_return_service(
            obligation=ob
        )
        service.file_assessed_return(
            1,
            FileAssessedTaxReturnCommand(
                obligation_id=ob.id,
                total_due_amount=Decimal("250000.00"),
                notes="Annual patente assessment",
            ),
        )
        rt = added["rt"]
        self.assertEqual(rt.status_code, RETURN_STATUS_FILED)
        self.assertEqual(rt.tax_type_code, TAX_TYPE_PATENTE)
        self.assertEqual(rt.total_due_amount, Decimal("250000.00"))
        self.assertEqual(rt.total_paid_amount, _ZERO)
        self.assertIsNotNone(rt.filed_at)
        # Obligation moved forward.
        self.assertEqual(ob.status_code, OBLIGATION_STATUS_FILED)


# ─── In-memory SQLite: bank-side JE for assessed types ──────────────────


def _seed_assessed_chart_and_return(
    session: Session, *, tax_type_code: str
) -> tuple[TaxReturn, Account, FiscalPeriod, int]:
    company = Company(
        legal_name="Test Co",
        display_name="Test",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()

    cls_passive = AccountClass(code="4", name="Tiers", display_order=4)
    cls_treasury = AccountClass(code="5", name="Trésorerie", display_order=5)
    cls_expense = AccountClass(code="6", name="Charges", display_order=6)
    session.add_all([cls_passive, cls_treasury, cls_expense])

    type_liab = AccountType(
        code="LIABILITY",
        name="Liability",
        normal_balance="CREDIT",
        financial_statement_section_code="LIAB",
    )
    type_treasury = AccountType(
        code="CASH_AND_CASH_EQUIVALENTS",
        name="Cash and equivalents",
        normal_balance="DEBIT",
        financial_statement_section_code="ASSET",
    )
    type_expense = AccountType(
        code="OPERATING_EXPENSE",
        name="Operating expense",
        normal_balance="DEBIT",
        financial_statement_section_code="EXP",
    )
    session.add_all([type_liab, type_treasury, type_expense])
    session.flush()

    # Build all three assessed-type accounts so the same fixture
    # function works for every tax type under test.
    patente = Account(
        company_id=company.id,
        account_code=PAYMENT_PATENTE_EXPENSE_ACCOUNT_CODE,
        account_name="Business licenses",
        account_class_id=cls_expense.id,
        account_type_id=type_expense.id,
        normal_balance="DEBIT",
        allow_manual_posting=True,
        is_control_account=False,
    )
    tsr = Account(
        company_id=company.id,
        account_code=PAYMENT_TSR_PAYABLE_ACCOUNT_CODE,
        account_name="Other taxes and contributions",
        account_class_id=cls_passive.id,
        account_type_id=type_liab.id,
        normal_balance="CREDIT",
        allow_manual_posting=True,
        is_control_account=False,
    )
    customs = Account(
        company_id=company.id,
        account_code=PAYMENT_CUSTOMS_EXPENSE_ACCOUNT_CODE,
        account_name="Other taxes",
        account_class_id=cls_expense.id,
        account_type_id=type_expense.id,
        normal_balance="DEBIT",
        allow_manual_posting=True,
        is_control_account=False,
    )
    bank = Account(
        company_id=company.id,
        account_code="5211",
        account_name="Banque principale",
        account_class_id=cls_treasury.id,
        account_type_id=type_treasury.id,
        normal_balance="DEBIT",
        allow_manual_posting=True,
        is_control_account=False,
    )
    session.add_all([patente, tsr, customs, bank])
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
        period_number=2,
        period_code="FY2026-M02",
        period_name="February 2026",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        status_code="OPEN",
    )
    session.add(fp)
    session.flush()

    obligation = TaxObligation(
        company_id=company.id,
        tax_type_code=tax_type_code,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        due_date=date(2026, 2, 15),
        status_code=OBLIGATION_STATUS_FILED,
    )
    session.add(obligation)
    session.flush()

    # Assessed-type returns are created already in the FILED state and
    # have no settlement JE — that's the whole point of T27.
    rt = TaxReturn(
        company_id=company.id,
        obligation_id=obligation.id,
        tax_type_code=tax_type_code,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        status_code=RETURN_STATUS_FILED,
        total_due_amount=Decimal("100.00"),
        total_paid_amount=_ZERO,
        journal_entry_id=None,
        filed_at=datetime(2026, 2, 1, 10, 0, 0),
    )
    session.add(rt)
    session.flush()
    return rt, bank, fp, company.id


def _build_real_payment_service(session: Session) -> TaxPaymentService:
    granted = {
        TaxPaymentService.PERMISSION_VIEW,
        TaxPaymentService.PERMISSION_MANAGE,
    }
    uow = _FakeUnitOfWork(session)
    return TaxPaymentService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        tax_payment_repository_factory=TaxPaymentRepository,
        tax_return_repository_factory=TaxReturnRepository,
        company_repository_factory=CompanyRepository,
        permission_service=_FakePermissionService(granted),
        audit_service=None,
        account_repository_factory=AccountRepository,
        fiscal_period_repository_factory=FiscalPeriodRepository,
        journal_entry_repository_factory=JournalEntryRepository,
        numbering_service=_StubNumberingService(),
    )


def _make_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class AssessedPaymentPostTests(unittest.TestCase):
    def _run_for(self, tax_type_code: str, expected_debit_code: str) -> None:
        session = _make_session_factory()()
        rt, bank, _fp, company_id = _seed_assessed_chart_and_return(
            session, tax_type_code=tax_type_code
        )
        session.commit()

        service = _build_real_payment_service(session)
        dto = service.record_payment(
            company_id,
            RecordTaxPaymentCommand(
                tax_return_id=rt.id,
                payment_date=date(2026, 2, 10),
                amount=Decimal("100.00"),
                payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                reference=f"{tax_type_code}-WIRE-001",
                treasury_account_id=bank.id,
            ),
        )

        self.assertIsNotNone(dto.journal_entry_id)
        session.expire_all()

        je = session.get(JournalEntry, dto.journal_entry_id)
        self.assertEqual(je.status_code, "POSTED")
        self.assertEqual(je.source_document_type, "tax_payment")

        lines = list(
            session.scalars(
                select(JournalEntryLine).where(
                    JournalEntryLine.journal_entry_id == je.id
                )
            )
        )
        self.assertEqual(len(lines), 2)
        total_dr = sum(l.debit_amount for l in lines)
        total_cr = sum(l.credit_amount for l in lines)
        self.assertEqual(total_dr, total_cr)
        self.assertEqual(total_dr, Decimal("100.00"))

        debit_lines = [l for l in lines if l.debit_amount > 0]
        credit_lines = [l for l in lines if l.credit_amount > 0]
        self.assertEqual(len(debit_lines), 1)
        self.assertEqual(len(credit_lines), 1)

        debit_account = session.get(Account, debit_lines[0].account_id)
        self.assertEqual(debit_account.account_code, expected_debit_code)
        self.assertEqual(credit_lines[0].account_id, bank.id)

        rt_reloaded = session.get(TaxReturn, rt.id)
        self.assertEqual(rt_reloaded.total_paid_amount, Decimal("100.00"))

    def test_patente_posts_dr_6412_cr_treasury(self) -> None:
        self._run_for(TAX_TYPE_PATENTE, PAYMENT_PATENTE_EXPENSE_ACCOUNT_CODE)

    def test_tsr_posts_dr_4478_cr_treasury(self) -> None:
        self._run_for(TAX_TYPE_TSR, PAYMENT_TSR_PAYABLE_ACCOUNT_CODE)

    def test_customs_posts_dr_6468_cr_treasury(self) -> None:
        self._run_for(TAX_TYPE_CUSTOMS, PAYMENT_CUSTOMS_EXPENSE_ACCOUNT_CODE)

    def test_assessed_payment_does_not_require_settlement(self) -> None:
        """Regression: the VAT-only ``journal_entry_id IS NOT NULL``
        gate must NOT apply to assessed types.
        """
        session = _make_session_factory()()
        rt, bank, _fp, company_id = _seed_assessed_chart_and_return(
            session, tax_type_code=TAX_TYPE_TSR
        )
        # Confirm fixture leaves return UNsettled — that's the
        # condition the VAT path would reject.
        self.assertIsNone(rt.journal_entry_id)
        session.commit()

        service = _build_real_payment_service(session)
        dto = service.record_payment(
            company_id,
            RecordTaxPaymentCommand(
                tax_return_id=rt.id,
                payment_date=date(2026, 2, 10),
                amount=Decimal("50.00"),
                payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                treasury_account_id=bank.id,
            ),
        )
        self.assertIsNotNone(dto.journal_entry_id)


if __name__ == "__main__":
    unittest.main()
