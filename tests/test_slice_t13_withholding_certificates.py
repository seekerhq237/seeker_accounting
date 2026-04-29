"""Slice T13 tests — withholding-tax certificate register service.

Exercises the ``WithholdingTaxCertificateService`` with mocked
repositories and unit-of-work, plus a real in-memory SQLite test for
the repository ``aggregate_totals`` method.
"""

from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure all ORM models are registered.
from seeker_accounting.db import model_registry  # noqa: F401
from seeker_accounting.db.base import Base
from seeker_accounting.modules.taxation.constants import (
    WHT_COUNTERPARTY_CUSTOMER,
    WHT_COUNTERPARTY_SUPPLIER,
    WHT_DIRECTION_INBOUND,
    WHT_DIRECTION_OUTBOUND,
    WHT_STATUS_ISSUED,
    WHT_STATUS_RECEIVED,
    WHT_STATUS_VOIDED,
)
from seeker_accounting.modules.taxation.dto.withholding_tax_certificate_dto import (
    RecordWithholdingTaxCertificateCommand,
    UpdateWithholdingTaxCertificateCommand,
    VoidWithholdingTaxCertificateCommand,
)
from seeker_accounting.modules.taxation.models.withholding_tax_certificate import (
    WithholdingTaxCertificate,
)
from seeker_accounting.modules.taxation.repositories.withholding_tax_certificate_repository import (
    WithholdingTaxCertificateRepository,
)
from seeker_accounting.modules.taxation.services.withholding_tax_certificate_service import (
    WithholdingTaxCertificateService,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


# ---------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------


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
    existing: list[WithholdingTaxCertificate] | None = None,
):
    if granted is None:
        granted = {
            WithholdingTaxCertificateService.PERMISSION_VIEW,
            WithholdingTaxCertificateService.PERMISSION_MANAGE,
        }
    uow = _FakeUnitOfWork()

    storage: list[WithholdingTaxCertificate] = list(existing or [])
    next_id = {"v": (max((c.id or 0 for c in storage), default=0) + 1)}

    repo = MagicMock(name="WithholdingTaxCertificateRepository")

    def _get_by_id(company_id: int, certificate_id: int):
        for c in storage:
            if c.company_id == company_id and c.id == certificate_id:
                return c
        return None

    def _add(certificate: WithholdingTaxCertificate):
        certificate.id = next_id["v"]
        next_id["v"] += 1
        storage.append(certificate)
        return certificate

    def _save(certificate: WithholdingTaxCertificate):
        return certificate

    def _find_existing(
        company_id: int,
        direction: str,
        certificate_number: str,
        exclude_id: int | None = None,
    ):
        for c in storage:
            if (
                c.company_id == company_id
                and c.direction == direction
                and c.certificate_number == certificate_number
                and (exclude_id is None or c.id != exclude_id)
            ):
                return c
        return None

    def _list_by_company(
        company_id,
        *,
        direction=None,
        status_code=None,
        date_from=None,
        date_to=None,
    ):
        rows = [c for c in storage if c.company_id == company_id]
        if direction is not None:
            rows = [c for c in rows if c.direction == direction]
        if status_code is not None:
            rows = [c for c in rows if c.status_code == status_code]
        if date_from is not None:
            rows = [c for c in rows if c.certificate_date >= date_from]
        if date_to is not None:
            rows = [c for c in rows if c.certificate_date <= date_to]
        return sorted(rows, key=lambda c: (c.certificate_date, c.id), reverse=True)

    repo.get_by_id.side_effect = _get_by_id
    repo.add.side_effect = _add
    repo.save.side_effect = _save
    repo.find_existing_certificate_number.side_effect = _find_existing
    repo.list_by_company.side_effect = _list_by_company
    repo.aggregate_totals.return_value = (0, Decimal("0.00"), Decimal("0.00"))

    company_repo = MagicMock(name="CompanyRepository")
    company_repo.get_by_id.return_value = (
        SimpleNamespace(id=1, name="Acme") if company_exists else None
    )

    app_context = SimpleNamespace(current_user_id=42)
    service = WithholdingTaxCertificateService(
        unit_of_work_factory=lambda: uow,
        app_context=app_context,
        certificate_repository_factory=lambda session: repo,
        company_repository_factory=lambda session: company_repo,
        permission_service=_FakePermissionService(granted),
        audit_service=None,
    )
    return service, repo, uow, storage


def _record_cmd(**overrides) -> RecordWithholdingTaxCertificateCommand:
    base = dict(
        direction=WHT_DIRECTION_INBOUND,
        counterparty_kind=WHT_COUNTERPARTY_CUSTOMER,
        counterparty_id=10,
        counterparty_name="Customer Co",
        counterparty_niu="P987654",
        tax_code_id=5,
        certificate_number="WHT-0001",
        certificate_date=date(2026, 3, 15),
        taxable_base=Decimal("1000.00"),
        tax_amount=Decimal("100.00"),
        fiscal_period_id=None,
        source_document_type=None,
        source_document_id=None,
        evidence_attachment_path=None,
        notes=None,
    )
    base.update(overrides)
    return RecordWithholdingTaxCertificateCommand(**base)


# ---------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------


class RecordCertificateTests(unittest.TestCase):
    def test_record_inbound_sets_received_status(self) -> None:
        service, _, uow, storage = _build_service()
        dto = service.record_certificate(1, _record_cmd(), actor_user_id=42)
        self.assertEqual(dto.direction, WHT_DIRECTION_INBOUND)
        self.assertEqual(dto.status_code, WHT_STATUS_RECEIVED)
        self.assertEqual(dto.tax_amount, Decimal("100.00"))
        self.assertEqual(dto.recorded_by_user_id, 42)
        self.assertTrue(uow.committed)
        self.assertEqual(len(storage), 1)

    def test_record_outbound_sets_issued_status(self) -> None:
        service, _, _, _ = _build_service()
        dto = service.record_certificate(
            1,
            _record_cmd(
                direction=WHT_DIRECTION_OUTBOUND,
                counterparty_kind=WHT_COUNTERPARTY_SUPPLIER,
                counterparty_name="Supplier Co",
            ),
        )
        self.assertEqual(dto.status_code, WHT_STATUS_ISSUED)

    def test_duplicate_number_per_direction_rejected(self) -> None:
        service, _, _, _ = _build_service()
        service.record_certificate(1, _record_cmd())
        with self.assertRaises(ConflictError):
            service.record_certificate(1, _record_cmd())

    def test_same_number_different_direction_allowed(self) -> None:
        service, _, _, storage = _build_service()
        service.record_certificate(1, _record_cmd())
        service.record_certificate(
            1,
            _record_cmd(
                direction=WHT_DIRECTION_OUTBOUND,
                counterparty_kind=WHT_COUNTERPARTY_SUPPLIER,
                counterparty_name="Supplier Co",
            ),
        )
        self.assertEqual(len(storage), 2)

    def test_invalid_direction_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.record_certificate(1, _record_cmd(direction="WEIRD"))

    def test_invalid_counterparty_kind_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.record_certificate(1, _record_cmd(counterparty_kind="ALIEN"))

    def test_negative_taxable_base_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.record_certificate(
                1, _record_cmd(taxable_base=Decimal("-1.00"))
            )

    def test_tax_exceeds_base_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.record_certificate(
                1,
                _record_cmd(
                    taxable_base=Decimal("100.00"),
                    tax_amount=Decimal("101.00"),
                ),
            )

    def test_blank_counterparty_name_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.record_certificate(1, _record_cmd(counterparty_name="   "))

    def test_blank_certificate_number_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.record_certificate(1, _record_cmd(certificate_number=""))

    def test_company_must_exist(self) -> None:
        service, _, _, _ = _build_service(company_exists=False)
        with self.assertRaises(NotFoundError):
            service.record_certificate(1, _record_cmd())

    def test_record_requires_manage_permission(self) -> None:
        service, _, _, _ = _build_service(
            granted={WithholdingTaxCertificateService.PERMISSION_VIEW}
        )
        with self.assertRaises(PermissionDeniedError):
            service.record_certificate(1, _record_cmd())


class UpdateCertificateTests(unittest.TestCase):
    def _seed(self, service):
        return service.record_certificate(1, _record_cmd())

    def test_update_changes_fields_but_preserves_direction(self) -> None:
        service, _, _, _ = _build_service()
        dto = self._seed(service)
        updated = service.update_certificate(
            1,
            UpdateWithholdingTaxCertificateCommand(
                certificate_id=dto.id,
                counterparty_kind=WHT_COUNTERPARTY_CUSTOMER,
                counterparty_id=10,
                counterparty_name="Customer Co Renamed",
                counterparty_niu="P987654",
                tax_code_id=5,
                certificate_number="WHT-0001",
                certificate_date=date(2026, 3, 16),
                taxable_base=Decimal("2000.00"),
                tax_amount=Decimal("200.00"),
                fiscal_period_id=None,
                source_document_type=None,
                source_document_id=None,
                evidence_attachment_path=None,
                notes="Edited",
            ),
        )
        self.assertEqual(updated.direction, WHT_DIRECTION_INBOUND)
        self.assertEqual(updated.counterparty_name, "Customer Co Renamed")
        self.assertEqual(updated.taxable_base, Decimal("2000.00"))
        self.assertEqual(updated.tax_amount, Decimal("200.00"))

    def test_update_rejects_duplicate_number(self) -> None:
        service, _, _, _ = _build_service()
        first = self._seed(service)
        second = service.record_certificate(
            1, _record_cmd(certificate_number="WHT-0002")
        )
        with self.assertRaises(ConflictError):
            service.update_certificate(
                1,
                UpdateWithholdingTaxCertificateCommand(
                    certificate_id=second.id,
                    counterparty_kind=WHT_COUNTERPARTY_CUSTOMER,
                    counterparty_id=10,
                    counterparty_name="Customer Co",
                    counterparty_niu=None,
                    tax_code_id=5,
                    certificate_number="WHT-0001",  # collides with `first`
                    certificate_date=date(2026, 3, 15),
                    taxable_base=Decimal("1000.00"),
                    tax_amount=Decimal("100.00"),
                    fiscal_period_id=None,
                    source_document_type=None,
                    source_document_id=None,
                    evidence_attachment_path=None,
                    notes=None,
                ),
            )
        # Reference unused-binding silencer
        self.assertEqual(first.certificate_number, "WHT-0001")

    def test_update_voided_certificate_rejected(self) -> None:
        service, _, _, _ = _build_service()
        dto = self._seed(service)
        service.void_certificate(
            1, VoidWithholdingTaxCertificateCommand(certificate_id=dto.id, reason="x")
        )
        with self.assertRaises(ValidationError):
            service.update_certificate(
                1,
                UpdateWithholdingTaxCertificateCommand(
                    certificate_id=dto.id,
                    counterparty_kind=WHT_COUNTERPARTY_CUSTOMER,
                    counterparty_id=None,
                    counterparty_name="Whatever",
                    counterparty_niu=None,
                    tax_code_id=5,
                    certificate_number="WHT-0001",
                    certificate_date=date(2026, 3, 15),
                    taxable_base=Decimal("1.00"),
                    tax_amount=Decimal("0.00"),
                    fiscal_period_id=None,
                    source_document_type=None,
                    source_document_id=None,
                    evidence_attachment_path=None,
                    notes=None,
                ),
            )

    def test_update_unknown_certificate_raises_notfound(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(NotFoundError):
            service.update_certificate(
                1,
                UpdateWithholdingTaxCertificateCommand(
                    certificate_id=999,
                    counterparty_kind=WHT_COUNTERPARTY_CUSTOMER,
                    counterparty_id=None,
                    counterparty_name="X",
                    counterparty_niu=None,
                    tax_code_id=5,
                    certificate_number="WHT-X",
                    certificate_date=date(2026, 1, 1),
                    taxable_base=Decimal("1.00"),
                    tax_amount=Decimal("0.10"),
                    fiscal_period_id=None,
                    source_document_type=None,
                    source_document_id=None,
                    evidence_attachment_path=None,
                    notes=None,
                ),
            )


class VoidCertificateTests(unittest.TestCase):
    def test_void_sets_status_and_appends_reason(self) -> None:
        service, _, _, _ = _build_service()
        dto = service.record_certificate(1, _record_cmd(notes="initial"))
        voided = service.void_certificate(
            1,
            VoidWithholdingTaxCertificateCommand(
                certificate_id=dto.id, reason="duplicate of WHT-0007"
            ),
        )
        self.assertEqual(voided.status_code, WHT_STATUS_VOIDED)
        self.assertIn("[VOIDED]", voided.notes or "")
        self.assertIn("duplicate of WHT-0007", voided.notes or "")

    def test_void_twice_rejected(self) -> None:
        service, _, _, _ = _build_service()
        dto = service.record_certificate(1, _record_cmd())
        service.void_certificate(
            1, VoidWithholdingTaxCertificateCommand(certificate_id=dto.id, reason=None)
        )
        with self.assertRaises(ValidationError):
            service.void_certificate(
                1,
                VoidWithholdingTaxCertificateCommand(
                    certificate_id=dto.id, reason=None
                ),
            )


class ListAndAggregateTests(unittest.TestCase):
    def test_list_filters_by_direction(self) -> None:
        service, _, _, _ = _build_service()
        service.record_certificate(1, _record_cmd(certificate_number="A"))
        service.record_certificate(
            1,
            _record_cmd(
                direction=WHT_DIRECTION_OUTBOUND,
                counterparty_kind=WHT_COUNTERPARTY_SUPPLIER,
                counterparty_name="Sup",
                certificate_number="B",
            ),
        )
        inbound = service.list_certificates(1, direction=WHT_DIRECTION_INBOUND)
        outbound = service.list_certificates(1, direction=WHT_DIRECTION_OUTBOUND)
        self.assertEqual(len(inbound), 1)
        self.assertEqual(len(outbound), 1)

    def test_list_invalid_direction_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.list_certificates(1, direction="ZZZ")

    def test_aggregate_invalid_date_window_rejected(self) -> None:
        service, _, _, _ = _build_service()
        with self.assertRaises(ValidationError):
            service.aggregate_totals(
                1,
                direction=WHT_DIRECTION_INBOUND,
                date_from=date(2026, 12, 31),
                date_to=date(2026, 1, 1),
            )


# ---------------------------------------------------------------------
# Real-DB repository test for aggregate_totals (incl. voided exclusion)
# ---------------------------------------------------------------------


def _make_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )


def _seed_company_and_tax_code(session: Session) -> tuple[int, int]:
    from seeker_accounting.modules.companies.models.company import Company
    from seeker_accounting.modules.accounting.reference_data.models.tax_code import (
        TaxCode,
    )

    company = Company(
        legal_name="Test Co",
        display_name="Test",
        country_code="CM",
        base_currency_code="XAF",
    )
    session.add(company)
    session.flush()

    tax_code = TaxCode(
        company_id=company.id,
        code="WHT-TSR-2.2",
        name="TSR 2.2%",
        tax_type_code="WHT",
        calculation_method_code="PERCENT_OF_BASE",
        rate_percent=Decimal("2.2"),
        is_recoverable=False,
        effective_from=date(2026, 1, 1),
        is_active=True,
    )
    session.add(tax_code)
    session.flush()
    return company.id, tax_code.id


class AggregateTotalsRepositoryTests(unittest.TestCase):
    def test_aggregate_excludes_voided_by_default(self) -> None:
        sf = _make_session_factory()
        with sf() as session:
            company_id, tax_code_id = _seed_company_and_tax_code(session)

            def _row(number, base, amount, status):
                return WithholdingTaxCertificate(
                    company_id=company_id,
                    fiscal_period_id=None,
                    direction=WHT_DIRECTION_INBOUND,
                    counterparty_kind=WHT_COUNTERPARTY_CUSTOMER,
                    counterparty_id=None,
                    counterparty_name="X",
                    counterparty_niu=None,
                    tax_code_id=tax_code_id,
                    certificate_number=number,
                    certificate_date=date(2026, 3, 15),
                    source_document_type=None,
                    source_document_id=None,
                    taxable_base=base,
                    tax_amount=amount,
                    evidence_attachment_path=None,
                    status_code=status,
                    notes=None,
                    recorded_by_user_id=None,
                )

            session.add(_row("A", Decimal("1000.00"), Decimal("100.00"), WHT_STATUS_RECEIVED))
            session.add(_row("B", Decimal("500.00"), Decimal("50.00"), WHT_STATUS_RECEIVED))
            session.add(_row("C", Decimal("300.00"), Decimal("30.00"), WHT_STATUS_VOIDED))
            session.commit()

            repo = WithholdingTaxCertificateRepository(session)
            count, total_base, total_amount = repo.aggregate_totals(
                company_id,
                direction=WHT_DIRECTION_INBOUND,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 12, 31),
            )
            self.assertEqual(count, 2)
            self.assertEqual(total_base, Decimal("1500.00"))
            self.assertEqual(total_amount, Decimal("150.00"))

            # include_voided=True picks up everything
            count_all, total_base_all, total_amount_all = repo.aggregate_totals(
                company_id,
                direction=WHT_DIRECTION_INBOUND,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 12, 31),
                include_voided=True,
            )
            self.assertEqual(count_all, 3)
            self.assertEqual(total_base_all, Decimal("1800.00"))
            self.assertEqual(total_amount_all, Decimal("180.00"))


if __name__ == "__main__":
    unittest.main()
