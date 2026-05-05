"""Tests for the deferrals module.

Covers:
- Line generation arithmetic (even split + rounding absorption)
- Schedule creation via service
- Activate / cancel state transitions
- EXPENSE posting JE direction
- REVENUE posting JE direction
- _advance_schedule_if_complete promotion
- post_all_due batch posting
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import seeker_accounting.db.model_registry  # noqa: F401  (register all mappers)
from seeker_accounting.db.base import Base
from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
from seeker_accounting.modules.accounting.chart_of_accounts.models.account import Account
from seeker_accounting.modules.accounting.deferrals.dto.deferral_dto import (
    ActivateDeferralScheduleCommand,
    CancelDeferralScheduleCommand,
    CreateDeferralScheduleCommand,
    PostAllDueCommand,
    PostRecognitionLineCommand,
)
from seeker_accounting.modules.accounting.deferrals.models.deferral_schedule import (
    DEFERRAL_STATUS_ACTIVE,
    DEFERRAL_STATUS_CANCELLED,
    DEFERRAL_STATUS_COMPLETE,
    DEFERRAL_STATUS_DRAFT,
    DEFERRAL_TYPE_EXPENSE,
    DEFERRAL_TYPE_REVENUE,
    LINE_STATUS_PENDING,
    LINE_STATUS_POSTED,
)
from seeker_accounting.modules.accounting.deferrals.repositories.deferral_repository import (
    DeferralRepository,
)
from seeker_accounting.modules.accounting.deferrals.services.deferral_service import (
    DeferralService,
)
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import FiscalYear
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.journals.models.journal_entry import JournalEntry
from seeker_accounting.modules.accounting.journals.repositories.journal_entry_repository import (
    JournalEntryRepository,
)
from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.platform.exceptions import ConflictError, ValidationError


# -- Stubs -------------------------------------------------------------------


class _StubNumberingService:
    def __init__(self) -> None:
        self._counter = 0

    def issue_next_number(self, session: Session, company_id: int, document_type_code: str) -> str:
        self._counter += 1
        return f"DFRRL-{self._counter:04d}"


# -- Seed helpers -------------------------------------------------------------


def _seed_db(session: Session):
    """Seed company, reference data, two accounts, one open fiscal period.

    Returns (company_id, holding_account_id, recognition_account_id, fiscal_period_id).
    """
    company = Company(
        legal_name="Deferral Test Co",
        display_name="Deferral Test Co",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()

    acls = AccountClass(code="6", name="Expenses", display_order=6)
    session.add(acls)

    atype_asset = AccountType(
        code="ASSET",
        name="Asset",
        normal_balance="DEBIT",
        financial_statement_section_code="ASSET",
    )
    atype_exp = AccountType(
        code="EXPENSE",
        name="Expense",
        normal_balance="DEBIT",
        financial_statement_section_code="IS",
    )
    session.add_all([atype_asset, atype_exp])
    session.flush()

    holding = Account(
        company_id=company.id,
        account_code="476100",
        account_name="Prepaid Expenses",
        account_class_id=acls.id,
        account_type_id=atype_asset.id,
        normal_balance="DEBIT",
        allow_manual_posting=True,
        is_control_account=False,
    )
    recognition = Account(
        company_id=company.id,
        account_code="622100",
        account_name="Licence Expense",
        account_class_id=acls.id,
        account_type_id=atype_exp.id,
        normal_balance="DEBIT",
        allow_manual_posting=True,
        is_control_account=False,
    )
    session.add_all([holding, recognition])
    session.flush()

    fp = FiscalPeriod(
        company_id=company.id,
        fiscal_year_id=None,  # will set below
        period_number=1,
        period_code="FY2025-01",
        period_name="January 2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        status_code="OPEN",
        is_adjustment_period=False,
    )
    # Need a FiscalYear first
    fy = FiscalYear(
        company_id=company.id,
        year_code="FY2025",
        year_name="Fiscal Year 2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        status_code="OPEN",
    )
    session.add(fy)
    session.flush()
    fp.fiscal_year_id = fy.id
    session.add(fp)
    session.flush()

    return company.id, holding.id, recognition.id, fp.id


def _make_service(SF: sessionmaker) -> DeferralService:
    uow_factory = create_unit_of_work_factory(SF)
    return DeferralService(
        unit_of_work_factory=uow_factory,
        deferral_repository_factory=lambda session: DeferralRepository(session),
        fiscal_period_repository_factory=lambda session: FiscalPeriodRepository(session),
        journal_entry_repository_factory=lambda session: JournalEntryRepository(session),
        numbering_service=_StubNumberingService(),
    )


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF: sessionmaker = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    session = SF()
    try:
        company_id, holding_id, recognition_id, period_id = _seed_db(session)
        session.commit()
    finally:
        session.close()
    service = _make_service(SF)
    return service, SF, company_id, holding_id, recognition_id, period_id


def _create_cmd(
    company_id: int,
    holding_id: int,
    recognition_id: int,
    *,
    deferral_type: str = DEFERRAL_TYPE_EXPENSE,
    total_amount: str = "1200.00",
    period_count: int = 12,
    start_date: date = date(2025, 1, 1),
) -> CreateDeferralScheduleCommand:
    return CreateDeferralScheduleCommand(
        company_id=company_id,
        deferral_type=deferral_type,
        description="Test deferral",
        total_amount=Decimal(total_amount),
        recognition_account_id=recognition_id,
        holding_account_id=holding_id,
        start_date=start_date,
        period_count=period_count,
        created_by_user_id=1,
    )


# -- Line generation tests ----------------------------------------------------


class LineGenerationTests(unittest.TestCase):

    @staticmethod
    def _gen(total: str, periods: int, start: date):
        return DeferralService._generate_lines(
            schedule_id=0,
            start_date=start,
            period_count=periods,
            total_amount=Decimal(total),
        )

    def test_even_split_sums_to_total(self) -> None:
        lines = self._gen("1200.00", 12, date(2025, 1, 1))
        self.assertEqual(sum(ln.amount for ln in lines), Decimal("1200.00"))

    def test_even_split_count(self) -> None:
        self.assertEqual(len(self._gen("1200.00", 12, date(2025, 1, 1))), 12)

    def test_each_even_line_is_100(self) -> None:
        lines = self._gen("1200.00", 12, date(2025, 1, 1))
        for ln in lines[:-1]:
            self.assertEqual(ln.amount, Decimal("100.00"))

    def test_rounding_absorbed_in_last_line(self) -> None:
        # 10 / 3 produces a rounding difference; sum must still be exact
        lines = self._gen("10.00", 3, date(2025, 1, 1))
        self.assertEqual(sum(ln.amount for ln in lines), Decimal("10.00"))

    def test_recognition_dates_are_month_end(self) -> None:
        lines = self._gen("300.00", 3, date(2025, 1, 15))
        self.assertEqual(lines[0].recognition_date, date(2025, 1, 31))
        self.assertEqual(lines[1].recognition_date, date(2025, 2, 28))
        self.assertEqual(lines[2].recognition_date, date(2025, 3, 31))

    def test_single_period(self) -> None:
        lines = self._gen("500.00", 1, date(2025, 6, 1))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].amount, Decimal("500.00"))

    def test_line_status_is_pending(self) -> None:
        lines = self._gen("300.00", 3, date(2025, 1, 1))
        for ln in lines:
            self.assertEqual(ln.status_code, LINE_STATUS_PENDING)


# -- Schedule creation tests --------------------------------------------------


class DeferralScheduleCreateTests(unittest.TestCase):

    def test_create_returns_id(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid))
        self.assertGreater(sid, 0)

    def test_create_generates_correct_line_count(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid, period_count=6))
        dto = service.get_schedule(cid, sid)
        self.assertEqual(len(dto.lines), 6)

    def test_create_status_is_draft(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid))
        self.assertEqual(service.get_schedule(cid, sid).status_code, DEFERRAL_STATUS_DRAFT)

    def test_create_rejects_negative_amount(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        with self.assertRaises(ValidationError):
            service.create_schedule(_create_cmd(cid, hid, rid, total_amount="-100"))

    def test_create_rejects_zero_periods(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        with self.assertRaises(ValidationError):
            service.create_schedule(_create_cmd(cid, hid, rid, period_count=0))

    def test_create_rejects_missing_description(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        cmd = CreateDeferralScheduleCommand(
            company_id=cid,
            deferral_type=DEFERRAL_TYPE_EXPENSE,
            description="",
            total_amount=Decimal("100.00"),
            recognition_account_id=rid,
            holding_account_id=hid,
            start_date=date(2025, 1, 1),
            period_count=3,
            created_by_user_id=1,
        )
        with self.assertRaises(ValidationError):
            service.create_schedule(cmd)


# -- Activation tests ---------------------------------------------------------


class DeferralActivationTests(unittest.TestCase):

    def test_activate_transitions_to_active(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        self.assertEqual(service.get_schedule(cid, sid).status_code, DEFERRAL_STATUS_ACTIVE)

    def test_activate_already_active_raises(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        with self.assertRaises((ConflictError, ValidationError)):
            service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))


# -- Cancel tests -------------------------------------------------------------


class DeferralCancelTests(unittest.TestCase):

    def test_cancel_draft(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid))
        service.cancel_schedule(CancelDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        self.assertEqual(service.get_schedule(cid, sid).status_code, DEFERRAL_STATUS_CANCELLED)

    def test_cancel_active(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        service.cancel_schedule(CancelDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        self.assertEqual(service.get_schedule(cid, sid).status_code, DEFERRAL_STATUS_CANCELLED)

    def test_cannot_cancel_cancelled(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid))
        service.cancel_schedule(CancelDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        with self.assertRaises((ConflictError, ValidationError)):
            service.cancel_schedule(CancelDeferralScheduleCommand(company_id=cid, schedule_id=sid))


# -- Posting tests ------------------------------------------------------------


class DeferralPostingTests(unittest.TestCase):

    def test_je_is_balanced(self) -> None:
        service, SF, cid, hid, rid, pid = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid, period_count=1, total_amount="300.00"))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        dto = service.get_schedule(cid, sid)
        je_id = service.post_recognition_line(PostRecognitionLineCommand(
            company_id=cid, schedule_id=sid, line_id=dto.lines[0].id,
            fiscal_period_id=pid, posted_by_user_id=1,
        ))
        session = SF()
        try:
            je = session.get(JournalEntry, je_id)
            dr = sum(ln.debit_amount or Decimal(0) for ln in je.lines)
            cr = sum(ln.credit_amount or Decimal(0) for ln in je.lines)
            self.assertEqual(dr, cr)
        finally:
            session.close()

    def test_expense_je_direction(self) -> None:
        """Expense: Dr recognition_account / Cr holding_account."""
        service, SF, cid, hid, rid, pid = _setup()
        sid = service.create_schedule(_create_cmd(
            cid, hid, rid, deferral_type=DEFERRAL_TYPE_EXPENSE, period_count=1, total_amount="100.00"
        ))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        dto = service.get_schedule(cid, sid)
        je_id = service.post_recognition_line(PostRecognitionLineCommand(
            company_id=cid, schedule_id=sid, line_id=dto.lines[0].id,
            fiscal_period_id=pid, posted_by_user_id=1,
        ))
        session = SF()
        try:
            je = session.get(JournalEntry, je_id)
            dr_line = next(ln for ln in je.lines if (ln.debit_amount or Decimal(0)) > 0)
            cr_line = next(ln for ln in je.lines if (ln.credit_amount or Decimal(0)) > 0)
            self.assertEqual(dr_line.account_id, rid)
            self.assertEqual(cr_line.account_id, hid)
        finally:
            session.close()

    def test_revenue_je_direction(self) -> None:
        """Revenue: Dr holding_account / Cr recognition_account."""
        service, SF, cid, hid, rid, pid = _setup()
        sid = service.create_schedule(_create_cmd(
            cid, hid, rid, deferral_type=DEFERRAL_TYPE_REVENUE, period_count=1, total_amount="200.00"
        ))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        dto = service.get_schedule(cid, sid)
        je_id = service.post_recognition_line(PostRecognitionLineCommand(
            company_id=cid, schedule_id=sid, line_id=dto.lines[0].id,
            fiscal_period_id=pid, posted_by_user_id=1,
        ))
        session = SF()
        try:
            je = session.get(JournalEntry, je_id)
            dr_line = next(ln for ln in je.lines if (ln.debit_amount or Decimal(0)) > 0)
            cr_line = next(ln for ln in je.lines if (ln.credit_amount or Decimal(0)) > 0)
            self.assertEqual(dr_line.account_id, hid)
            self.assertEqual(cr_line.account_id, rid)
        finally:
            session.close()

    def test_posting_stamps_line_je_id(self) -> None:
        service, _, cid, hid, rid, pid = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid, period_count=1))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        dto = service.get_schedule(cid, sid)
        je_id = service.post_recognition_line(PostRecognitionLineCommand(
            company_id=cid, schedule_id=sid, line_id=dto.lines[0].id,
            fiscal_period_id=pid, posted_by_user_id=1,
        ))
        dto2 = service.get_schedule(cid, sid)
        self.assertEqual(dto2.lines[0].status_code, LINE_STATUS_POSTED)
        self.assertEqual(dto2.lines[0].journal_entry_id, je_id)

    def test_all_posted_advances_to_complete(self) -> None:
        service, _, cid, hid, rid, pid = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid, period_count=1))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        dto = service.get_schedule(cid, sid)
        service.post_recognition_line(PostRecognitionLineCommand(
            company_id=cid, schedule_id=sid, line_id=dto.lines[0].id,
            fiscal_period_id=pid, posted_by_user_id=1,
        ))
        self.assertEqual(service.get_schedule(cid, sid).status_code, DEFERRAL_STATUS_COMPLETE)

    def test_post_all_due_batch(self) -> None:
        service, _, cid, hid, rid, pid = _setup()
        sid = service.create_schedule(_create_cmd(
            cid, hid, rid, period_count=3, total_amount="300.00", start_date=date(2025, 1, 1)
        ))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        count = service.post_all_due(PostAllDueCommand(
            company_id=cid, fiscal_period_id=pid, as_of_date=date(2025, 3, 31), posted_by_user_id=1,
        ))
        self.assertEqual(len(count), 3)
        self.assertEqual(service.get_schedule(cid, sid).status_code, DEFERRAL_STATUS_COMPLETE)


# -- List / DTO tests ---------------------------------------------------------


class DeferralListTests(unittest.TestCase):

    def test_list_empty(self) -> None:
        service, _, cid, _, _, _ = _setup()
        self.assertEqual(service.list_schedules(cid), [])

    def test_list_returns_created(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        service.create_schedule(_create_cmd(cid, hid, rid))
        self.assertEqual(len(service.list_schedules(cid)), 1)

    def test_list_filters_by_type(self) -> None:
        service, _, cid, hid, rid, _ = _setup()
        service.create_schedule(_create_cmd(cid, hid, rid, deferral_type=DEFERRAL_TYPE_EXPENSE))
        service.create_schedule(_create_cmd(cid, hid, rid, deferral_type=DEFERRAL_TYPE_REVENUE))
        result = service.list_schedules(cid, deferral_type=DEFERRAL_TYPE_EXPENSE)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].deferral_type, DEFERRAL_TYPE_EXPENSE)

    def test_posted_and_remaining_amounts(self) -> None:
        service, _, cid, hid, rid, pid = _setup()
        sid = service.create_schedule(_create_cmd(cid, hid, rid, period_count=2, total_amount="200.00"))
        service.activate_schedule(ActivateDeferralScheduleCommand(company_id=cid, schedule_id=sid))
        dto = service.get_schedule(cid, sid)
        self.assertEqual(dto.posted_amount, Decimal("0.00"))
        self.assertEqual(dto.remaining_amount, Decimal("200.00"))

        service.post_recognition_line(PostRecognitionLineCommand(
            company_id=cid, schedule_id=sid, line_id=dto.lines[0].id,
            fiscal_period_id=pid, posted_by_user_id=1,
        ))
        dto2 = service.get_schedule(cid, sid)
        self.assertEqual(dto2.posted_amount, Decimal("100.00"))
        self.assertEqual(dto2.remaining_amount, Decimal("100.00"))


if __name__ == "__main__":
    unittest.main()
