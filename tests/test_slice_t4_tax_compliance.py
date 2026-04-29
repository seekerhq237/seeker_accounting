"""Slice T4 tests — tax obligations, returns, payments.

Service surfaces are exercised through mocks (consistent with the
T1 ``CompanyTaxProfileService`` test pattern). VAT box aggregation
from posted source documents is exercised at the mapper /
relationship level only; full end-to-end aggregation (which would
require seeding sales invoices and purchase bills through the
sales/purchase service stacks) is deferred to integration tests.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from seeker_accounting.db import model_registry  # noqa: F401

from seeker_accounting.modules.taxation.constants import (
    OBLIGATION_STATUS_OPEN,
    RETURN_STATUS_DRAFT,
    TAX_PAYMENT_METHOD_BANK_TRANSFER,
    TAX_TYPE_CIT_INSTALLMENT,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    CreateTaxObligationCommand,
    GenerateMonthlyVATObligationsCommand,
    GenerateQuarterlyCITInstallmentsCommand,
    RecordTaxPaymentCommand,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.models.tax_payment import TaxPayment
from seeker_accounting.modules.taxation.models.tax_return import TaxReturn
from seeker_accounting.modules.taxation.models.tax_return_line import TaxReturnLine
from seeker_accounting.modules.taxation.services.tax_obligation_service import (
    TaxObligationService,
)
from seeker_accounting.modules.taxation.services.tax_payment_service import (
    TaxPaymentService,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


# ─── Test helpers ──────────────────────────────────────────────────────


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.session = MagicMock(name="Session")
        self.committed = False

    def __enter__(self) -> "_FakeUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


class _FakePermissionService:
    def __init__(self, granted: set[str]) -> None:
        self._granted = granted

    def require_permission(self, code: str) -> None:
        if code not in self._granted:
            raise PermissionDeniedError(f"Missing permission: {code}")


def _build_obligation_service(
    *,
    granted: set[str] | None = None,
    company_exists: bool = True,
    obligations_by_period: dict | None = None,
    obligations_by_id: dict | None = None,
):
    if granted is None:
        granted = {
            TaxObligationService.PERMISSION_VIEW,
            TaxObligationService.PERMISSION_MANAGE,
        }

    uow = _FakeUnitOfWork()
    obligations_by_period = obligations_by_period or {}
    obligations_by_id = obligations_by_id or {}
    saved: list[TaxObligation] = []

    obligation_repo = MagicMock(name="TaxObligationRepository")
    obligation_repo.get_by_period.side_effect = (
        lambda company_id, tax_type_code, ps, pe: obligations_by_period.get(
            (company_id, tax_type_code, ps, pe)
        )
    )
    obligation_repo.get_by_id.side_effect = lambda company_id, obligation_id: (
        obligations_by_id.get(obligation_id)
    )
    obligation_repo.list_by_company.return_value = list(obligations_by_id.values())
    obligation_repo.add.side_effect = lambda o: (saved.append(o) or o)

    company_repo = MagicMock(name="CompanyRepository")
    company_repo.get_by_id.return_value = (
        SimpleNamespace(id=1, name="Acme") if company_exists else None
    )

    service = TaxObligationService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        tax_obligation_repository_factory=lambda session: obligation_repo,
        company_repository_factory=lambda session: company_repo,
        permission_service=_FakePermissionService(granted),
        audit_service=None,
    )
    return service, obligation_repo, company_repo, uow, saved


# ─── Obligation service ────────────────────────────────────────────────


class CreateTaxObligationTests(unittest.TestCase):
    def test_creates_obligation_when_none_exists(self) -> None:
        service, repo, _, uow, saved = _build_obligation_service()
        dto = service.create_obligation(
            1,
            CreateTaxObligationCommand(
                tax_type_code=TAX_TYPE_VAT,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                due_date=date(2026, 2, 15),
            ),
        )
        self.assertEqual(dto.tax_type_code, TAX_TYPE_VAT)
        self.assertEqual(dto.status_code, OBLIGATION_STATUS_OPEN)
        self.assertTrue(uow.committed)
        self.assertEqual(len(saved), 1)

    def test_rejects_duplicate_obligation(self) -> None:
        existing = TaxObligation(
            id=10,
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            due_date=date(2026, 2, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        service, _, _, _, _ = _build_obligation_service(
            obligations_by_period={
                (1, TAX_TYPE_VAT, date(2026, 1, 1), date(2026, 1, 31)): existing
            },
            obligations_by_id={10: existing},
        )
        with self.assertRaises(ConflictError):
            service.create_obligation(
                1,
                CreateTaxObligationCommand(
                    tax_type_code=TAX_TYPE_VAT,
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                    due_date=date(2026, 2, 15),
                ),
            )

    def test_rejects_due_date_before_period_end(self) -> None:
        service, _, _, _, _ = _build_obligation_service()
        with self.assertRaises(ValidationError):
            service.create_obligation(
                1,
                CreateTaxObligationCommand(
                    tax_type_code=TAX_TYPE_VAT,
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                    due_date=date(2026, 1, 20),
                ),
            )

    def test_rejects_unknown_tax_type(self) -> None:
        service, _, _, _, _ = _build_obligation_service()
        with self.assertRaises(ValidationError):
            service.create_obligation(
                1,
                CreateTaxObligationCommand(
                    tax_type_code="UNKNOWN",
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                    due_date=date(2026, 2, 15),
                ),
            )

    def test_rejects_when_missing_permission(self) -> None:
        service, _, _, _, _ = _build_obligation_service(granted=set())
        with self.assertRaises(PermissionDeniedError):
            service.create_obligation(
                1,
                CreateTaxObligationCommand(
                    tax_type_code=TAX_TYPE_VAT,
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                    due_date=date(2026, 2, 15),
                ),
            )

    def test_rejects_when_company_not_found(self) -> None:
        service, _, _, _, _ = _build_obligation_service(company_exists=False)
        with self.assertRaises(NotFoundError):
            service.create_obligation(
                1,
                CreateTaxObligationCommand(
                    tax_type_code=TAX_TYPE_VAT,
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                    due_date=date(2026, 2, 15),
                ),
            )


class GenerateMonthlyVATObligationsTests(unittest.TestCase):
    def test_creates_twelve_obligations_when_none_exist(self) -> None:
        service, _, _, _, saved = _build_obligation_service()
        dtos = service.generate_monthly_vat_obligations(
            1, GenerateMonthlyVATObligationsCommand(year=2026)
        )
        self.assertEqual(len(dtos), 12)
        self.assertEqual(len(saved), 12)
        # Each obligation due day = min(15, days in next month) → 15 always.
        for i, dto in enumerate(dtos, start=1):
            self.assertEqual(dto.tax_type_code, TAX_TYPE_VAT)
            self.assertEqual(dto.period_start.month, i)
            self.assertEqual(dto.due_date.day, 15)

    def test_idempotent_skips_existing(self) -> None:
        existing_jan = TaxObligation(
            id=1,
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            due_date=date(2026, 2, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        service, _, _, _, saved = _build_obligation_service(
            obligations_by_period={
                (1, TAX_TYPE_VAT, date(2026, 1, 1), date(2026, 1, 31)): existing_jan
            }
        )
        dtos = service.generate_monthly_vat_obligations(
            1, GenerateMonthlyVATObligationsCommand(year=2026)
        )
        self.assertEqual(len(dtos), 12)
        # Only 11 new ones appended (Jan was already there).
        self.assertEqual(len(saved), 11)

    def test_rejects_invalid_year(self) -> None:
        service, _, _, _, _ = _build_obligation_service()
        with self.assertRaises(ValidationError):
            service.generate_monthly_vat_obligations(
                1, GenerateMonthlyVATObligationsCommand(year=1500)
            )

    def test_rejects_invalid_due_day(self) -> None:
        service, _, _, _, _ = _build_obligation_service()
        with self.assertRaises(ValidationError):
            service.generate_monthly_vat_obligations(
                1,
                GenerateMonthlyVATObligationsCommand(
                    year=2026, due_day_of_next_month=31
                ),
            )


class GenerateQuarterlyCITInstallmentsTests(unittest.TestCase):
    def test_creates_four_obligations_when_none_exist(self) -> None:
        service, _, _, _, saved = _build_obligation_service()
        dtos = service.generate_quarterly_cit_installments(
            1, GenerateQuarterlyCITInstallmentsCommand(year=2026)
        )
        self.assertEqual(len(dtos), 4)
        self.assertEqual(len(saved), 4)
        # Q1: Jan-Mar due Apr 15
        self.assertEqual(dtos[0].tax_type_code, TAX_TYPE_CIT_INSTALLMENT)
        self.assertEqual(dtos[0].period_start, date(2026, 1, 1))
        self.assertEqual(dtos[0].period_end, date(2026, 3, 31))
        self.assertEqual(dtos[0].due_date, date(2026, 4, 15))
        # Q2: Apr-Jun due Jul 15
        self.assertEqual(dtos[1].period_start, date(2026, 4, 1))
        self.assertEqual(dtos[1].period_end, date(2026, 6, 30))
        self.assertEqual(dtos[1].due_date, date(2026, 7, 15))
        # Q3: Jul-Sep due Oct 15
        self.assertEqual(dtos[2].period_start, date(2026, 7, 1))
        self.assertEqual(dtos[2].period_end, date(2026, 9, 30))
        self.assertEqual(dtos[2].due_date, date(2026, 10, 15))
        # Q4: Oct-Dec due Jan 15 of next year
        self.assertEqual(dtos[3].period_start, date(2026, 10, 1))
        self.assertEqual(dtos[3].period_end, date(2026, 12, 31))
        self.assertEqual(dtos[3].due_date, date(2027, 1, 15))

    def test_idempotent_skips_existing(self) -> None:
        existing_q1 = TaxObligation(
            id=1,
            company_id=1,
            tax_type_code=TAX_TYPE_CIT_INSTALLMENT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            due_date=date(2026, 4, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        service, _, _, _, saved = _build_obligation_service(
            obligations_by_period={
                (1, TAX_TYPE_CIT_INSTALLMENT, date(2026, 1, 1), date(2026, 3, 31)): existing_q1
            }
        )
        dtos = service.generate_quarterly_cit_installments(
            1, GenerateQuarterlyCITInstallmentsCommand(year=2026)
        )
        self.assertEqual(len(dtos), 4)
        # Only 3 new ones (Q1 already exists).
        self.assertEqual(len(saved), 3)

    def test_rejects_invalid_year(self) -> None:
        service, _, _, _, _ = _build_obligation_service()
        with self.assertRaises(ValidationError):
            service.generate_quarterly_cit_installments(
                1, GenerateQuarterlyCITInstallmentsCommand(year=1500)
            )

    def test_rejects_invalid_due_day(self) -> None:
        service, _, _, _, _ = _build_obligation_service()
        with self.assertRaises(ValidationError):
            service.generate_quarterly_cit_installments(
                1,
                GenerateQuarterlyCITInstallmentsCommand(
                    year=2026, due_day_of_next_month=31
                ),
            )

    def test_requires_manage_permission(self) -> None:
        service, _, _, _, _ = _build_obligation_service(granted=set())
        with self.assertRaises(PermissionDeniedError):
            service.generate_quarterly_cit_installments(
                1, GenerateQuarterlyCITInstallmentsCommand(year=2026)
            )


class CancelTaxObligationTests(unittest.TestCase):
    def test_cancels_open_obligation(self) -> None:
        obligation = TaxObligation(
            id=10,
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            due_date=date(2026, 2, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        # Empty returns collection means no returns exist.
        service, _, _, uow, _ = _build_obligation_service(
            obligations_by_id={10: obligation}
        )
        dto = service.cancel_obligation(1, 10)
        self.assertEqual(dto.status_code, "CANCELLED")
        self.assertTrue(uow.committed)

    def test_blocks_cancel_when_returns_exist(self) -> None:
        obligation = TaxObligation(
            id=10,
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            due_date=date(2026, 2, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        existing_return = TaxReturn(
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            status_code=RETURN_STATUS_DRAFT,
            total_due_amount=Decimal("0.00"),
            total_paid_amount=Decimal("0.00"),
        )
        obligation.tax_returns.append(existing_return)
        service, _, _, _, _ = _build_obligation_service(
            obligations_by_id={10: obligation}
        )
        with self.assertRaises(ValidationError):
            service.cancel_obligation(1, 10)


# ─── Payment service ───────────────────────────────────────────────────


def _build_payment_service(
    *,
    granted: set[str] | None = None,
    tax_return: TaxReturn | None = None,
):
    if granted is None:
        granted = {
            TaxPaymentService.PERMISSION_VIEW,
            TaxPaymentService.PERMISSION_MANAGE,
        }

    uow = _FakeUnitOfWork()
    saved_payments: list[TaxPayment] = []

    payment_repo = MagicMock(name="TaxPaymentRepository")
    payment_repo.add.side_effect = lambda p: (saved_payments.append(p) or p)
    payment_repo.list_by_return.return_value = []

    return_repo = MagicMock(name="TaxReturnRepository")
    return_repo.get_by_id.return_value = tax_return

    company_repo = MagicMock(name="CompanyRepository")
    company_repo.get_by_id.return_value = SimpleNamespace(id=1, name="Acme")

    service = TaxPaymentService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        tax_payment_repository_factory=lambda session: payment_repo,
        tax_return_repository_factory=lambda session: return_repo,
        company_repository_factory=lambda session: company_repo,
        permission_service=_FakePermissionService(granted),
        audit_service=None,
    )
    return service, payment_repo, return_repo, uow, saved_payments


class RecordTaxPaymentTests(unittest.TestCase):
    def _make_return(self, *, due: str = "100.00", paid: str = "0.00") -> TaxReturn:
        obligation = TaxObligation(
            id=10,
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            due_date=date(2026, 2, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        tax_return = TaxReturn(
            id=20,
            company_id=1,
            obligation_id=10,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            status_code=RETURN_STATUS_DRAFT,
            total_due_amount=Decimal(due),
            total_paid_amount=Decimal(paid),
        )
        tax_return.obligation = obligation
        return tax_return

    def test_records_payment_and_updates_total_paid(self) -> None:
        tax_return = self._make_return(due="100.00", paid="0.00")
        service, _, _, uow, saved = _build_payment_service(tax_return=tax_return)
        dto = service.record_payment(
            1,
            RecordTaxPaymentCommand(
                tax_return_id=20,
                payment_date=date(2026, 2, 10),
                amount=Decimal("60.00"),
                payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
            ),
        )
        self.assertEqual(dto.amount, Decimal("60.00"))
        self.assertEqual(tax_return.total_paid_amount, Decimal("60.00"))
        # Not fully paid yet — obligation stays open.
        self.assertEqual(tax_return.obligation.status_code, OBLIGATION_STATUS_OPEN)
        self.assertTrue(uow.committed)
        self.assertEqual(len(saved), 1)

    def test_marks_obligation_paid_when_fully_settled(self) -> None:
        tax_return = self._make_return(due="100.00", paid="40.00")
        service, _, _, _, _ = _build_payment_service(tax_return=tax_return)
        service.record_payment(
            1,
            RecordTaxPaymentCommand(
                tax_return_id=20,
                payment_date=date(2026, 2, 10),
                amount=Decimal("60.00"),
                payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
            ),
        )
        self.assertEqual(tax_return.total_paid_amount, Decimal("100.00"))
        self.assertEqual(tax_return.obligation.status_code, "PAID")

    def test_rejects_zero_amount(self) -> None:
        tax_return = self._make_return()
        service, _, _, _, _ = _build_payment_service(tax_return=tax_return)
        with self.assertRaises(ValidationError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=20,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("0.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                ),
            )

    def test_rejects_unknown_payment_method(self) -> None:
        tax_return = self._make_return()
        service, _, _, _, _ = _build_payment_service(tax_return=tax_return)
        with self.assertRaises(ValidationError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=20,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("50.00"),
                    payment_method_code="MAGIC_BEAN",
                ),
            )

    def test_rejects_payment_before_period_start(self) -> None:
        tax_return = self._make_return()
        service, _, _, _, _ = _build_payment_service(tax_return=tax_return)
        with self.assertRaises(ValidationError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=20,
                    payment_date=date(2025, 12, 1),
                    amount=Decimal("50.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                ),
            )

    def test_rejects_payment_against_missing_return(self) -> None:
        service, _, _, _, _ = _build_payment_service(tax_return=None)
        with self.assertRaises(NotFoundError):
            service.record_payment(
                1,
                RecordTaxPaymentCommand(
                    tax_return_id=99,
                    payment_date=date(2026, 2, 10),
                    amount=Decimal("50.00"),
                    payment_method_code=TAX_PAYMENT_METHOD_BANK_TRANSFER,
                ),
            )


# ─── Mapper relationships ──────────────────────────────────────────────


class TaxReturnRelationshipTests(unittest.TestCase):
    def test_tax_return_carries_lines_and_payments_collections(self) -> None:
        tax_return = TaxReturn(
            company_id=1,
            obligation_id=10,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            status_code=RETURN_STATUS_DRAFT,
            total_due_amount=Decimal("0.00"),
            total_paid_amount=Decimal("0.00"),
        )
        tax_return.lines.append(
            TaxReturnLine(
                box_code="VAT_OUTPUT",
                label="Output VAT",
                amount=Decimal("19.25"),
                sort_order=0,
            )
        )
        self.assertEqual(len(tax_return.lines), 1)
        self.assertEqual(tax_return.lines[0].amount, Decimal("19.25"))

    def test_tax_obligation_back_populates_returns(self) -> None:
        obligation = TaxObligation(
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            due_date=date(2026, 2, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        tax_return = TaxReturn(
            company_id=1,
            tax_type_code=TAX_TYPE_VAT,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            status_code=RETURN_STATUS_DRAFT,
            total_due_amount=Decimal("0.00"),
            total_paid_amount=Decimal("0.00"),
        )
        obligation.tax_returns.append(tax_return)
        self.assertIs(tax_return.obligation, obligation)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
