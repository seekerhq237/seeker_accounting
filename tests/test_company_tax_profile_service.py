"""Unit tests for ``CompanyTaxProfileService``.

The service has narrow surface area (one read, one write) so we mock
the repositories and unit-of-work rather than spinning up a real
database — which keeps these as fast unit tests rather than
integration tests.
"""

from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

# Ensure all ORM models are registered before SQLAlchemy configures mappers
# triggered by instantiating ``CompanyTaxProfile`` below.
from seeker_accounting.db import model_registry  # noqa: F401

from seeker_accounting.modules.taxation.dto.company_tax_profile_dto import (
    UpsertCompanyTaxProfileCommand,
)
from seeker_accounting.modules.taxation.models.company_tax_profile import (
    CompanyTaxProfile,
)
from seeker_accounting.modules.taxation.services.company_tax_profile_service import (
    CompanyTaxProfileService,
)
from seeker_accounting.platform.exceptions import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


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
    existing_profile: CompanyTaxProfile | None = None,
):
    if granted is None:
        granted = {
            CompanyTaxProfileService.PERMISSION_VIEW,
            CompanyTaxProfileService.PERMISSION_MANAGE,
        }

    uow = _FakeUnitOfWork()

    profile_repo = MagicMock(name="CompanyTaxProfileRepository")
    profile_repo.get_by_company.return_value = existing_profile
    profile_repo.add.side_effect = lambda p: p
    profile_repo.save.side_effect = lambda p: p

    company_repo = MagicMock(name="CompanyRepository")
    company_repo.get_by_id.return_value = (
        SimpleNamespace(id=1, name="Acme") if company_exists else None
    )

    app_context = SimpleNamespace(current_user_id=42)
    permission_service = _FakePermissionService(granted)

    service = CompanyTaxProfileService(
        unit_of_work_factory=lambda: uow,
        app_context=app_context,
        company_tax_profile_repository_factory=lambda session: profile_repo,
        company_repository_factory=lambda session: company_repo,
        permission_service=permission_service,
        audit_service=None,
    )
    return service, profile_repo, company_repo, uow


class GetOrDefaultTests(unittest.TestCase):
    def test_returns_default_when_no_row(self) -> None:
        service, repo, _, _ = _build_service(existing_profile=None)
        dto = service.get_or_default(1)
        self.assertFalse(dto.exists)
        self.assertEqual(dto.company_id, 1)
        self.assertIsNone(dto.niu)
        self.assertFalse(dto.is_vat_liable)
        repo.get_by_company.assert_called_once_with(1)

    def test_returns_existing_profile(self) -> None:
        existing = CompanyTaxProfile(
            company_id=1,
            niu="P12345",
            tax_regime_code="REAL",
            is_vat_liable=True,
            vat_effective_from=date(2024, 1, 1),
            sme_qualified_flag=False,
            otp_enabled_flag=False,
            default_withholding_applicable_flag=False,
        )
        service, _, _, _ = _build_service(existing_profile=existing)
        dto = service.get_or_default(1)
        self.assertTrue(dto.exists)
        self.assertEqual(dto.niu, "P12345")
        self.assertEqual(dto.tax_regime_code, "REAL")
        self.assertTrue(dto.is_vat_liable)

    def test_raises_for_unknown_company(self) -> None:
        service, _, _, _ = _build_service(company_exists=False)
        with self.assertRaises(NotFoundError):
            service.get_or_default(99)

    def test_requires_view_permission(self) -> None:
        service, _, _, _ = _build_service(granted=set())
        with self.assertRaises(PermissionDeniedError):
            service.get_or_default(1)


class UpsertTests(unittest.TestCase):
    def test_creates_profile_when_absent(self) -> None:
        service, repo, _, uow = _build_service(existing_profile=None)
        dto = service.upsert(
            1,
            UpsertCompanyTaxProfileCommand(
                niu="P12345",
                tax_center_code="DGE",
                taxpayer_segment_code="LARGE",
                tax_regime_code="REAL",
                is_vat_liable=True,
                vat_effective_from=date(2024, 1, 1),
                cit_rate_profile_code="STANDARD",
                dsf_form_code="DSF_REAL",
                dsf_submission_mode_code="EXCEL",
            ),
        )
        self.assertTrue(dto.exists)
        self.assertEqual(dto.niu, "P12345")
        self.assertEqual(dto.tax_regime_code, "REAL")
        self.assertEqual(dto.updated_by_user_id, 42)
        self.assertTrue(uow.committed)
        repo.add.assert_called_once()

    def test_updates_existing_profile(self) -> None:
        existing = CompanyTaxProfile(
            company_id=1,
            niu="OLD",
            is_vat_liable=False,
            sme_qualified_flag=False,
            otp_enabled_flag=False,
            default_withholding_applicable_flag=False,
        )
        service, repo, _, uow = _build_service(existing_profile=existing)
        dto = service.upsert(
            1,
            UpsertCompanyTaxProfileCommand(
                niu="NEW",
                is_vat_liable=True,
                vat_effective_from=date(2025, 6, 1),
            ),
        )
        self.assertEqual(dto.niu, "NEW")
        self.assertTrue(dto.is_vat_liable)
        self.assertTrue(uow.committed)
        repo.add.assert_not_called()

    def test_requires_manage_permission(self) -> None:
        service, _, _, _ = _build_service(
            granted={CompanyTaxProfileService.PERMISSION_VIEW}
        )
        with self.assertRaises(PermissionDeniedError):
            service.upsert(1, UpsertCompanyTaxProfileCommand())

    def test_unknown_company_raises_not_found(self) -> None:
        service, _, _, _ = _build_service(company_exists=False)
        with self.assertRaises(NotFoundError):
            service.upsert(99, UpsertCompanyTaxProfileCommand())

    def test_vat_liable_requires_effective_date(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.upsert(
                1, UpsertCompanyTaxProfileCommand(is_vat_liable=True)
            )

    def test_unknown_regime_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.upsert(
                1, UpsertCompanyTaxProfileCommand(tax_regime_code="MADEUP")
            )

    def test_unknown_dsf_form_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.upsert(
                1, UpsertCompanyTaxProfileCommand(dsf_form_code="DSF_NOPE")
            )

    def test_unknown_segment_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.upsert(
                1, UpsertCompanyTaxProfileCommand(taxpayer_segment_code="XYZ")
            )

    def test_codes_normalized_to_upper(self) -> None:
        service, _, _, _ = _build_service()
        dto = service.upsert(
            1,
            UpsertCompanyTaxProfileCommand(
                tax_regime_code="real",
                dsf_form_code="dsf_real",
                taxpayer_segment_code="large",
            ),
        )
        self.assertEqual(dto.tax_regime_code, "REAL")
        self.assertEqual(dto.dsf_form_code, "DSF_REAL")
        self.assertEqual(dto.taxpayer_segment_code, "LARGE")

    def test_blank_niu_normalizes_to_none(self) -> None:
        service, _, _, _ = _build_service()
        dto = service.upsert(
            1, UpsertCompanyTaxProfileCommand(niu="   ")
        )
        self.assertIsNone(dto.niu)

    def test_overlong_niu_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.upsert(
                1, UpsertCompanyTaxProfileCommand(niu="X" * 51)
            )

    def test_actor_user_id_override(self) -> None:
        service, _, _, _ = _build_service(existing_profile=None)
        dto = service.upsert(
            1,
            UpsertCompanyTaxProfileCommand(),
            actor_user_id=999,
        )
        self.assertEqual(dto.updated_by_user_id, 999)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
