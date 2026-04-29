"""Slice T18-T21 tests — withholding / Patente / TSR / customs obligations.

Service-layer tests for the four obligation generators added in slices
T18 (monthly withholding), T19 (annual Patente), T20 (monthly TSR), and
T21 (per-declaration customs duty). UI integration is deferred to a
later consolidated slice.

These tests follow the mock-based pattern established in
``test_slice_t4_tax_compliance.py``: the unit of work, repositories,
and permission service are stubbed so we can exercise the generator
methods in isolation.
"""

from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from seeker_accounting.db import model_registry  # noqa: F401
from seeker_accounting.modules.taxation.constants import (
    OBLIGATION_STATUS_OPEN,
    TAX_TYPE_CUSTOMS,
    TAX_TYPE_PATENTE,
    TAX_TYPE_TSR,
    TAX_TYPE_WITHHOLDING,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    CreateCustomsDutyObligationCommand,
    GenerateAnnualPatenteObligationCommand,
    GenerateMonthlyTSRObligationsCommand,
    GenerateMonthlyWithholdingObligationsCommand,
)
from seeker_accounting.modules.taxation.models.tax_obligation import TaxObligation
from seeker_accounting.modules.taxation.services.tax_obligation_service import (
    TaxObligationService,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


# ─── Test helpers (mirrors test_slice_t4_tax_compliance.py) ────────────


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


def _build_service(
    *,
    granted: set[str] | None = None,
    company_exists: bool = True,
    obligations_by_period: dict | None = None,
):
    if granted is None:
        granted = {
            TaxObligationService.PERMISSION_VIEW,
            TaxObligationService.PERMISSION_MANAGE,
        }

    uow = _FakeUnitOfWork()
    obligations_by_period = obligations_by_period or {}
    saved: list[TaxObligation] = []

    obligation_repo = MagicMock(name="TaxObligationRepository")
    obligation_repo.get_by_period.side_effect = (
        lambda company_id, tax_type_code, ps, pe: obligations_by_period.get(
            (company_id, tax_type_code, ps, pe)
        )
    )

    def _add(obligation: TaxObligation) -> TaxObligation:
        # Simulate flush-assigned id so the audit call sees a value.
        if obligation.id is None:
            obligation.id = 1000 + len(saved)
        saved.append(obligation)
        return obligation

    obligation_repo.add.side_effect = _add

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
    return service, obligation_repo, uow, saved


# ─── T18: monthly withholding ──────────────────────────────────────────


class GenerateMonthlyWithholdingTests(unittest.TestCase):
    def test_creates_twelve_obligations_with_following_month_due_date(self) -> None:
        service, _, uow, saved = _build_service()

        dtos = service.generate_monthly_withholding_obligations(
            1, GenerateMonthlyWithholdingObligationsCommand(year=2026)
        )

        self.assertEqual(len(dtos), 12)
        self.assertEqual(len(saved), 12)
        self.assertTrue(uow.committed)
        for dto in dtos:
            self.assertEqual(dto.tax_type_code, TAX_TYPE_WITHHOLDING)
            self.assertEqual(dto.status_code, OBLIGATION_STATUS_OPEN)
        # January obligation -> period 2026-01-01..01-31, due 2026-02-15.
        jan = dtos[0]
        self.assertEqual(jan.period_start, date(2026, 1, 1))
        self.assertEqual(jan.period_end, date(2026, 1, 31))
        self.assertEqual(jan.due_date, date(2026, 2, 15))
        # December obligation due in January of the next year.
        dec = dtos[11]
        self.assertEqual(dec.period_start, date(2026, 12, 1))
        self.assertEqual(dec.period_end, date(2026, 12, 31))
        self.assertEqual(dec.due_date, date(2027, 1, 15))

    def test_idempotent_when_existing_period_present(self) -> None:
        existing = TaxObligation(
            id=99,
            company_id=1,
            tax_type_code=TAX_TYPE_WITHHOLDING,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            due_date=date(2026, 4, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        service, _, _, saved = _build_service(
            obligations_by_period={
                (1, TAX_TYPE_WITHHOLDING, date(2026, 3, 1), date(2026, 3, 31)): existing
            },
        )

        dtos = service.generate_monthly_withholding_obligations(
            1, GenerateMonthlyWithholdingObligationsCommand(year=2026)
        )

        self.assertEqual(len(dtos), 12)
        # Only 11 NEW rows added -- March was reused.
        self.assertEqual(len(saved), 11)

    def test_rejects_year_out_of_range(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.generate_monthly_withholding_obligations(
                1, GenerateMonthlyWithholdingObligationsCommand(year=1500)
            )

    def test_rejects_invalid_due_day(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.generate_monthly_withholding_obligations(
                1,
                GenerateMonthlyWithholdingObligationsCommand(
                    year=2026, due_day_of_next_month=29
                ),
            )

    def test_requires_manage_permission(self) -> None:
        service, _, _, _ = _build_service(granted=set())
        with self.assertRaises(PermissionDeniedError):
            service.generate_monthly_withholding_obligations(
                1, GenerateMonthlyWithholdingObligationsCommand(year=2026)
            )


# ─── T19: annual Patente ───────────────────────────────────────────────


class GenerateAnnualPatenteTests(unittest.TestCase):
    def test_creates_single_obligation_for_year(self) -> None:
        service, _, uow, saved = _build_service()

        dto = service.generate_annual_patente_obligation(
            1, GenerateAnnualPatenteObligationCommand(year=2026)
        )

        self.assertEqual(dto.tax_type_code, TAX_TYPE_PATENTE)
        self.assertEqual(dto.period_start, date(2026, 1, 1))
        self.assertEqual(dto.period_end, date(2026, 12, 31))
        self.assertEqual(dto.due_date, date(2026, 2, 28))
        self.assertEqual(dto.status_code, OBLIGATION_STATUS_OPEN)
        self.assertTrue(uow.committed)
        self.assertEqual(len(saved), 1)

    def test_idempotent_returns_existing_when_present(self) -> None:
        existing = TaxObligation(
            id=77,
            company_id=1,
            tax_type_code=TAX_TYPE_PATENTE,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            due_date=date(2026, 2, 28),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        service, _, uow, saved = _build_service(
            obligations_by_period={
                (1, TAX_TYPE_PATENTE, date(2026, 1, 1), date(2026, 12, 31)): existing
            },
        )

        dto = service.generate_annual_patente_obligation(
            1, GenerateAnnualPatenteObligationCommand(year=2026)
        )

        self.assertEqual(dto.id, 77)
        self.assertEqual(len(saved), 0)
        # No new commit required when the obligation already existed.
        self.assertFalse(uow.committed)

    def test_custom_due_date_honoured(self) -> None:
        service, _, _, _ = _build_service()

        dto = service.generate_annual_patente_obligation(
            1,
            GenerateAnnualPatenteObligationCommand(
                year=2026, due_month=3, due_day=15
            ),
        )

        self.assertEqual(dto.due_date, date(2026, 3, 15))

    def test_rejects_invalid_due_month(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.generate_annual_patente_obligation(
                1,
                GenerateAnnualPatenteObligationCommand(
                    year=2026, due_month=13, due_day=1
                ),
            )

    def test_rejects_invalid_due_day_for_month(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.generate_annual_patente_obligation(
                1,
                GenerateAnnualPatenteObligationCommand(
                    year=2026, due_month=2, due_day=30
                ),
            )

    def test_rejects_when_company_missing(self) -> None:
        service, _, _, _ = _build_service(company_exists=False)
        with self.assertRaises(NotFoundError):
            service.generate_annual_patente_obligation(
                999, GenerateAnnualPatenteObligationCommand(year=2026)
            )


# ─── T20: monthly TSR ──────────────────────────────────────────────────


class GenerateMonthlyTSRTests(unittest.TestCase):
    def test_creates_twelve_obligations(self) -> None:
        service, _, uow, saved = _build_service()

        dtos = service.generate_monthly_tsr_obligations(
            1, GenerateMonthlyTSRObligationsCommand(year=2027)
        )

        self.assertEqual(len(dtos), 12)
        self.assertEqual(len(saved), 12)
        self.assertTrue(uow.committed)
        for dto in dtos:
            self.assertEqual(dto.tax_type_code, TAX_TYPE_TSR)
        # Spot-check February in a leap year was handled by the
        # generator's calendar.monthrange call.
        feb = dtos[1]
        self.assertEqual(feb.period_end, date(2027, 2, 28))

    def test_idempotent_when_existing_periods(self) -> None:
        existing = TaxObligation(
            id=55,
            company_id=1,
            tax_type_code=TAX_TYPE_TSR,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            due_date=date(2026, 7, 15),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        service, _, _, saved = _build_service(
            obligations_by_period={
                (1, TAX_TYPE_TSR, date(2026, 6, 1), date(2026, 6, 30)): existing
            },
        )

        dtos = service.generate_monthly_tsr_obligations(
            1, GenerateMonthlyTSRObligationsCommand(year=2026)
        )

        self.assertEqual(len(dtos), 12)
        self.assertEqual(len(saved), 11)


# ─── T21: per-declaration customs duty ─────────────────────────────────


class CreateCustomsDutyTests(unittest.TestCase):
    def test_records_obligation_with_declaration_reference_in_notes(self) -> None:
        service, _, uow, saved = _build_service()

        dto = service.create_customs_duty_obligation(
            1,
            CreateCustomsDutyObligationCommand(
                declaration_date=date(2026, 4, 10),
                due_date=date(2026, 4, 25),
                declaration_reference="DECL-2026-0001",
            ),
        )

        self.assertEqual(dto.tax_type_code, TAX_TYPE_CUSTOMS)
        self.assertEqual(dto.period_start, date(2026, 4, 10))
        self.assertEqual(dto.period_end, date(2026, 4, 10))
        self.assertEqual(dto.due_date, date(2026, 4, 25))
        self.assertIn("DECL-2026-0001", dto.notes or "")
        self.assertTrue(uow.committed)
        self.assertEqual(len(saved), 1)

    def test_combines_reference_and_user_notes(self) -> None:
        service, _, _, _ = _build_service()

        dto = service.create_customs_duty_obligation(
            1,
            CreateCustomsDutyObligationCommand(
                declaration_date=date(2026, 4, 10),
                due_date=date(2026, 4, 25),
                declaration_reference="DECL-2026-0002",
                notes="Spare parts for press machine.",
            ),
        )

        notes = dto.notes or ""
        self.assertIn("DECL-2026-0002", notes)
        self.assertIn("Spare parts", notes)

    def test_rejects_due_before_declaration(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.create_customs_duty_obligation(
                1,
                CreateCustomsDutyObligationCommand(
                    declaration_date=date(2026, 4, 10),
                    due_date=date(2026, 4, 1),
                ),
            )

    def test_rejects_duplicate_declaration_date(self) -> None:
        existing = TaxObligation(
            id=88,
            company_id=1,
            tax_type_code=TAX_TYPE_CUSTOMS,
            period_start=date(2026, 4, 10),
            period_end=date(2026, 4, 10),
            due_date=date(2026, 4, 25),
            status_code=OBLIGATION_STATUS_OPEN,
        )
        service, _, _, _ = _build_service(
            obligations_by_period={
                (1, TAX_TYPE_CUSTOMS, date(2026, 4, 10), date(2026, 4, 10)): existing
            },
        )
        with self.assertRaises(ConflictError):
            service.create_customs_duty_obligation(
                1,
                CreateCustomsDutyObligationCommand(
                    declaration_date=date(2026, 4, 10),
                    due_date=date(2026, 4, 25),
                    declaration_reference="DECL-2026-0003",
                ),
            )

    def test_requires_manage_permission(self) -> None:
        service, _, _, _ = _build_service(granted=set())
        with self.assertRaises(PermissionDeniedError):
            service.create_customs_duty_obligation(
                1,
                CreateCustomsDutyObligationCommand(
                    declaration_date=date(2026, 4, 10),
                    due_date=date(2026, 4, 25),
                ),
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
