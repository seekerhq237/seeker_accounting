"""Slice T47 tests — VAT return state machine (review-lock-file).

Tests the 4-eye workflow:
  DRAFT → READY_FOR_REVIEW → APPROVED → FILED
          ↓
        DRAFT  (revert allowed from READY_FOR_REVIEW only)

Post-filing:
  FILED → SUBMITTED_AWAITING_CONFIRMATION → SUBMITTED_CONFIRMED
"""
from __future__ import annotations

import datetime
import unittest
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db import model_registry  # noqa: F401
from seeker_accounting.db.base import Base
from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_period import FiscalPeriod
from seeker_accounting.modules.accounting.fiscal_periods.models.fiscal_year import FiscalYear
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
from seeker_accounting.modules.taxation.repositories.tax_obligation_repository import TaxObligationRepository
from seeker_accounting.modules.taxation.repositories.tax_return_repository import TaxReturnRepository
from seeker_accounting.modules.taxation.services.tax_return_service import TaxReturnService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.taxation.constants import (
    RETURN_STATUS_APPROVED,
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_FILED,
    RETURN_STATUS_READY_FOR_REVIEW,
    RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION,
    RETURN_STATUS_SUBMITTED_CONFIRMED,
    TAX_TYPE_VAT,
)
from seeker_accounting.platform.exceptions import ValidationError


_ZERO = Decimal("0.00")


class _FakeUoW:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


def _perm_service(perms: set[str]):
    class _P:
        def require_permission(self, code):
            if code not in perms:
                from seeker_accounting.platform.exceptions import PermissionDeniedError
                raise PermissionDeniedError(f"Missing: {code}")
        def has_permission(self, code):
            return code in perms
    return _P()


def _make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    return SF()


def _seed_company(session: Session) -> Company:
    co = Company(
        legal_name="T47 Test Co", display_name="T47", country_code="CM",
        base_currency_code="XAF",
    )
    session.add(co)
    session.flush()
    return co


def _seed_obligation(session: Session, company_id: int) -> TaxObligation:
    obl = TaxObligation(
        company_id=company_id,
        tax_type_code=TAX_TYPE_VAT,
        period_start=datetime.date(2025, 1, 1),
        period_end=datetime.date(2025, 1, 31),
        due_date=datetime.date(2025, 2, 15),
        status_code="OPEN",
    )
    session.add(obl)
    session.flush()
    return obl


def _seed_return(
    session: Session, company_id: int, obligation_id: int,
    status_code: str = RETURN_STATUS_DRAFT,
) -> TaxReturn:
    tr = TaxReturn(
        company_id=company_id,
        obligation_id=obligation_id,
        tax_type_code=TAX_TYPE_VAT,
        period_start=datetime.date(2025, 1, 1),
        period_end=datetime.date(2025, 1, 31),
        status_code=status_code,
        total_due_amount=_ZERO,
        total_paid_amount=_ZERO,
    )
    session.add(tr)
    session.flush()
    return tr


def _build_service(session: Session, perms: set[str] | None = None) -> TaxReturnService:
    all_perms = perms if perms is not None else {
        TaxReturnService.PERMISSION_MANAGE,
        TaxReturnService.PERMISSION_VIEW,
        TaxReturnService.PERMISSION_FILE,
        TaxReturnService.PERMISSION_REVIEW,
        TaxReturnService.PERMISSION_APPROVE,
        TaxReturnService.PERMISSION_CONFIRM,
    }
    uow = _FakeUoW(session)
    return TaxReturnService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=1),
        tax_return_repository_factory=TaxReturnRepository,
        tax_obligation_repository_factory=TaxObligationRepository,
        company_repository_factory=CompanyRepository,
        posted_tax_line_repository_factory=lambda s: SimpleNamespace(),
        fiscal_period_repository_factory=lambda s: SimpleNamespace(),
        permission_service=_perm_service(all_perms),
        audit_service=None,
    )


class T47StatusConstantsTests(unittest.TestCase):
    """T47 constants are present in the constants module."""

    def test_all_t47_constants_importable(self) -> None:
        from seeker_accounting.modules.taxation.constants import (
            RETURN_STATUS_READY_FOR_REVIEW,
            RETURN_STATUS_APPROVED,
            RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION,
            RETURN_STATUS_SUBMITTED_CONFIRMED,
            ALL_RETURN_STATUS_CODES_EXTENDED,
        )
        self.assertEqual(RETURN_STATUS_READY_FOR_REVIEW, "READY_FOR_REVIEW")
        self.assertEqual(RETURN_STATUS_APPROVED, "APPROVED")
        self.assertIn(RETURN_STATUS_READY_FOR_REVIEW, ALL_RETURN_STATUS_CODES_EXTENDED)
        self.assertIn(RETURN_STATUS_APPROVED, ALL_RETURN_STATUS_CODES_EXTENDED)
        self.assertIn(RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION, ALL_RETURN_STATUS_CODES_EXTENDED)
        self.assertIn(RETURN_STATUS_SUBMITTED_CONFIRMED, ALL_RETURN_STATUS_CODES_EXTENDED)


class T47PermissionConstantsTests(unittest.TestCase):
    """T47 permission codes are on TaxReturnService."""

    def test_new_permission_attributes_exist(self) -> None:
        self.assertEqual(TaxReturnService.PERMISSION_REVIEW, "taxation.returns.review")
        self.assertEqual(TaxReturnService.PERMISSION_APPROVE, "taxation.returns.approve")
        self.assertEqual(TaxReturnService.PERMISSION_CONFIRM, "taxation.returns.confirm")


class T47StateMachineTests(unittest.TestCase):
    """State machine transition methods behave correctly."""

    def setUp(self) -> None:
        self.session = _make_session()
        self.co = _seed_company(self.session)
        self.obl = _seed_obligation(self.session, self.co.id)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_submit_for_review_transitions_draft_to_ready(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_DRAFT)
        self.session.commit()
        svc = _build_service(self.session)
        dto = svc.submit_for_review(self.co.id, tr.id)
        self.assertEqual(dto.status_code, RETURN_STATUS_READY_FOR_REVIEW)

    def test_submit_for_review_rejects_non_draft(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_READY_FOR_REVIEW)
        self.session.commit()
        svc = _build_service(self.session)
        with self.assertRaises(ValidationError):
            svc.submit_for_review(self.co.id, tr.id)

    def test_revert_to_draft_from_ready(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_READY_FOR_REVIEW)
        self.session.commit()
        svc = _build_service(self.session)
        dto = svc.revert_to_draft(self.co.id, tr.id)
        self.assertEqual(dto.status_code, RETURN_STATUS_DRAFT)

    def test_revert_to_draft_from_approved_is_rejected(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_APPROVED)
        self.session.commit()
        svc = _build_service(self.session)
        with self.assertRaises(ValidationError):
            svc.revert_to_draft(self.co.id, tr.id)

    def test_approve_return_from_ready_for_review(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_READY_FOR_REVIEW)
        self.session.commit()
        svc = _build_service(self.session)
        dto = svc.approve_return(self.co.id, tr.id)
        self.assertEqual(dto.status_code, RETURN_STATUS_APPROVED)

    def test_approve_return_rejects_draft(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_DRAFT)
        self.session.commit()
        svc = _build_service(self.session)
        with self.assertRaises(ValidationError):
            svc.approve_return(self.co.id, tr.id)

    def test_submit_return_from_filed(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_FILED)
        self.session.commit()
        svc = _build_service(self.session)
        dto = svc.submit_return(self.co.id, tr.id)
        self.assertEqual(dto.status_code, RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION)

    def test_submit_return_rejects_draft(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_DRAFT)
        self.session.commit()
        svc = _build_service(self.session)
        with self.assertRaises(ValidationError):
            svc.submit_return(self.co.id, tr.id)

    def test_confirm_submission(self) -> None:
        tr = _seed_return(
            self.session, self.co.id, self.obl.id,
            RETURN_STATUS_SUBMITTED_AWAITING_CONFIRMATION,
        )
        self.session.commit()
        svc = _build_service(self.session)
        dto = svc.confirm_submission(self.co.id, tr.id)
        self.assertEqual(dto.status_code, RETURN_STATUS_SUBMITTED_CONFIRMED)

    def test_confirm_submission_rejects_non_awaiting(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_FILED)
        self.session.commit()
        svc = _build_service(self.session)
        with self.assertRaises(ValidationError):
            svc.confirm_submission(self.co.id, tr.id)

    def test_approve_requires_approve_permission(self) -> None:
        tr = _seed_return(self.session, self.co.id, self.obl.id, RETURN_STATUS_READY_FOR_REVIEW)
        self.session.commit()
        svc = _build_service(self.session, perms={TaxReturnService.PERMISSION_VIEW})
        from seeker_accounting.platform.exceptions import PermissionDeniedError
        with self.assertRaises(PermissionDeniedError):
            svc.approve_return(self.co.id, tr.id)
