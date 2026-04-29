"""Slice T16 tests — bank-side journal entry on tax payment.

Covers the path where ``TaxPaymentService.record_payment`` posts a
``Dr 4441 / Cr <treasury>`` journal entry for a payment recorded
against an already-settled VAT return.

Three test classes:

- ``BankSideValidationTests`` — pure mock-based validation gates that
  do not need any data persistence.
- ``BankSidePostTests`` — full in-memory SQLite path that asserts the
  posted JE is balanced, links back to the payment, and stamps
  ``tax_payments.journal_entry_id``.
- ``LegacyPathStillWorksTests`` — when ``treasury_account_id`` is not
  supplied (e.g. non-VAT returns or legacy callers), record_payment
  must continue to record the payment row only, leaving
  ``journal_entry_id`` NULL.
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
    OBLIGATION_STATUS_OPEN,
    RETURN_STATUS_FILED,
    TAX_PAYMENT_METHOD_BANK_TRANSFER,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    RecordTaxPaymentCommand,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.models.tax_payment import TaxPayment
from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
from seeker_accounting.modules.taxation.repositories.tax_payment_repository import (
    TaxPaymentRepository,
)
from seeker_accounting.modules.taxation.repositories.tax_return_repository import (
    TaxReturnRepository,
)
from seeker_accounting.modules.taxation.services.tax_payment_service import (
    TaxPaymentService,
)
from seeker_accounting.platform.exceptions import (
    NotFoundError,
    PeriodLockedError,
    ValidationError,
)


_ZERO = Decimal("0.00")


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


# ─── Mock-based validation gates ────────────────────────────────────────


def _make_filed_vat_return(**overrides) -> TaxReturn:
    obligation = TaxObligation(
        id=10,
        company_id=1,
        tax_type_code=TAX_TYPE_VAT,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        due_date=date(2026, 2, 15),
        status_code=OBLIGATION_STATUS_OPEN,
    )
    defaults = dict(
        id=20,
        company_id=1,
        obligation_id=10,
        tax_type_code=TAX_TYPE_VAT,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        status_code=RETURN_STATUS_FILED,
        total_due_amount=Decimal("100.00"),
        total_paid_amount=_ZERO,
        journal_entry_id=999,  # Settled
    )
    defaults.update(overrides)
    rt = TaxReturn(**defaults)
    rt.obligation = obligation
    return rt


def _build_mock_payment_service(*, tax_return: TaxReturn | None):
    granted = {
        TaxPaymentService.PERMISSION_VIEW,
        TaxPaymentService.PERMISSION_MANAGE,
    }

    uow = _FakeUnitOfWork()
    payment_repo = MagicMock(name="TaxPaymentRepository")
    payment_repo.add.side_effect = lambda p: p
    payment_repo.list_by_return.return_value = []

    return_repo = MagicMock(name="TaxReturnRepository")
    return_repo.get_by_id.return_value = tax_return

    company_repo = MagicMock(name="CompanyRepository")
    company_repo.get_by_id.return_value = SimpleNamespace(id=1)

    account_repo = MagicMock(name="AccountRepository")
    period_repo = MagicMock(name="FiscalPeriodRepository")
    journal_repo = MagicMock(name="JournalEntryRepository")

    return TaxPaymentService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        tax_payment_repository_factory=lambda s: payment_repo,
        tax_return_repository_factory=lambda s: return_repo,
        company_repository_factory=lambda s: company_repo,
        permission_service=_FakePermissionService(granted),
        audit_service=None,
        account_repository_factory=lambda s: account_repo,
        fiscal_period_repository_factory=lambda s: period_repo,
        journal_entry_repository_factory=lambda s: journal_repo,
        numbering_service=_StubNumberingService(),
    ), account_repo, period_repo


class BankSideValidationTests(unittest.TestCase):
    def test_treasury_required_for_vat_rejected_when_unsettled(self) -> None:
        rt = _make_filed_vat_return(journal_entry_id=None)
        service, _, _ = _build_mock_payment_service(tax_return=rt)
        with self.assertRaises(ValidationError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=20,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("50.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                    treasury_account_id=300,
                ),
            )

    def test_non_vat_return_rejects_treasury_account(self) -> None:
        rt = _make_filed_vat_return(tax_type_code="CIT_INSTALLMENT")
        service, _, _ = _build_mock_payment_service(tax_return=rt)
        with self.assertRaises(ValidationError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=20,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("50.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                    treasury_account_id=300,
                ),
            )

    def test_missing_treasury_account_rejected(self) -> None:
        rt = _make_filed_vat_return()
        service, account_repo, _ = _build_mock_payment_service(tax_return=rt)
        account_repo.get_by_id.return_value = None
        with self.assertRaises(NotFoundError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=20,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("50.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                    treasury_account_id=999,
                ),
            )

    def test_inactive_treasury_account_rejected(self) -> None:
        rt = _make_filed_vat_return()
        service, account_repo, _ = _build_mock_payment_service(tax_return=rt)
        account_repo.get_by_id.return_value = SimpleNamespace(
            id=300,
            account_code="5211",
            is_active=False,
            allow_manual_posting=True,
        )
        with self.assertRaises(ValidationError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=20,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("50.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                    treasury_account_id=300,
                ),
            )

    def test_missing_payable_4441_rejected(self) -> None:
        rt = _make_filed_vat_return()
        service, account_repo, _ = _build_mock_payment_service(tax_return=rt)
        account_repo.get_by_id.return_value = SimpleNamespace(
            id=300,
            account_code="5211",
            is_active=True,
            allow_manual_posting=True,
        )
        account_repo.get_by_code.return_value = None
        with self.assertRaises(ValidationError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=20,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("50.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                    treasury_account_id=300,
                ),
            )


# ─── In-memory DB happy/unhappy paths ───────────────────────────────────


def _seed_chart_and_return(session: Session) -> tuple[TaxReturn, Account, FiscalPeriod, int]:
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
    session.add_all([cls_passive, cls_treasury])

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
    session.add_all([type_liab, type_treasury])
    session.flush()

    payable = Account(
        company_id=company.id,
        account_code="4441",
        account_name="État, TVA due",
        account_class_id=cls_passive.id,
        account_type_id=type_liab.id,
        normal_balance="CREDIT",
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
    session.add_all([payable, bank])
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

    # Anchor JE used as the "settlement journal" reference for the
    # return.  Its existence simply gives ``journal_entry_id`` a valid
    # FK target — the bank-side test does not exercise it directly.
    settlement_je = JournalEntry(
        company_id=company.id,
        fiscal_period_id=fp.id,
        entry_number="JE-SET-001",
        entry_date=date(2026, 1, 31),
        journal_type_code="OD",
        description="anchor",
        source_module_code="taxation",
        source_document_type="tax_return",
        source_document_id=1,
        status_code="POSTED",
        posted_at=datetime(2026, 1, 31, 10, 0, 0),
    )
    session.add(settlement_je)
    session.flush()

    obligation = TaxObligation(
        company_id=company.id,
        tax_type_code=TAX_TYPE_VAT,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        due_date=date(2026, 2, 15),
        status_code=OBLIGATION_STATUS_OPEN,
    )
    session.add(obligation)
    session.flush()
    rt = TaxReturn(
        company_id=company.id,
        obligation_id=obligation.id,
        tax_type_code=TAX_TYPE_VAT,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        status_code=RETURN_STATUS_FILED,
        total_due_amount=Decimal("100.00"),
        total_paid_amount=_ZERO,
        journal_entry_id=settlement_je.id,
        settled_at=datetime(2026, 1, 31, 10, 0, 0),
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


class BankSidePostTests(unittest.TestCase):
    def test_post_creates_balanced_je_and_links_payment(self) -> None:
        session = _make_session_factory()()
        rt, bank, _, company_id = _seed_chart_and_return(session)
        session.commit()

        service = _build_real_payment_service(session)
        dto = service.record_payment(
            company_id,
            RecordTaxPaymentCommand(
                tax_return_id=rt.id,
                payment_date=date(2026, 2, 10),
                amount=Decimal("100.00"),
                payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                reference="WIRE-2026-001",
                treasury_account_id=bank.id,
            ),
        )

        self.assertIsNotNone(dto.journal_entry_id)
        # Reload payment + JE.
        session.expire_all()
        payment = session.get(TaxPayment, dto.id)
        self.assertEqual(payment.journal_entry_id, dto.journal_entry_id)

        je = session.get(JournalEntry, dto.journal_entry_id)
        self.assertEqual(je.status_code, "POSTED")
        self.assertEqual(je.source_document_type, "tax_payment")
        self.assertEqual(je.source_document_id, payment.id)

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

        # Dr 4441 / Cr bank.
        debit_lines = [l for l in lines if l.debit_amount > 0]
        credit_lines = [l for l in lines if l.credit_amount > 0]
        self.assertEqual(len(debit_lines), 1)
        self.assertEqual(len(credit_lines), 1)
        self.assertEqual(credit_lines[0].account_id, bank.id)

        # Return total_paid updated.
        rt_reloaded = session.get(TaxReturn, rt.id)
        self.assertEqual(rt_reloaded.total_paid_amount, Decimal("100.00"))

    def test_locked_period_rejects_post(self) -> None:
        session = _make_session_factory()()
        rt, bank, fp, company_id = _seed_chart_and_return(session)
        fp.status_code = "LOCKED"
        session.commit()

        service = _build_real_payment_service(session)
        with self.assertRaises(PeriodLockedError):
            service.record_payment(
                company_id,
                RecordTaxPaymentCommand(
                    tax_return_id=rt.id,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("100.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                    treasury_account_id=bank.id,
                ),
            )


class LegacyPathStillWorksTests(unittest.TestCase):
    """Without ``treasury_account_id`` the service must record the row only."""

    def test_record_only_path_still_works(self) -> None:
        session = _make_session_factory()()
        rt, _, _, company_id = _seed_chart_and_return(session)
        session.commit()

        service = _build_real_payment_service(session)
        dto = service.record_payment(
            company_id,
            RecordTaxPaymentCommand(
                tax_return_id=rt.id,
                payment_date=date(2026, 2, 10),
                amount=Decimal("60.00"),
                payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
            ),
        )
        self.assertIsNone(dto.journal_entry_id)
        self.assertEqual(dto.amount, Decimal("60.00"))


if __name__ == "__main__":
    unittest.main()
