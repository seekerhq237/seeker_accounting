"""Slice T13 — link withholding certificate to a posted journal entry.

Tests the ``link_to_journal_entry`` service method end-to-end with a
mocked JE repository: success path, clearing the link, and the
validation rules (voided cert, missing JE, non-posted JE, missing
factory).
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

# Ensure all ORM models are registered (cross-module relationships).
from seeker_accounting.db import model_registry  # noqa: F401
from seeker_accounting.modules.taxation.constants import (
    WHT_COUNTERPARTY_CUSTOMER,
    WHT_DIRECTION_INBOUND,
    WHT_STATUS_RECEIVED,
    WHT_STATUS_VOIDED,
)
from seeker_accounting.modules.taxation.dto.withholding_tax_certificate_dto import (
    LinkWithholdingCertificateToJournalEntryCommand,
)
from seeker_accounting.modules.taxation.models.withholding_tax_certificate import (
    WithholdingTaxCertificate,
)
from seeker_accounting.modules.taxation.services.withholding_tax_certificate_service import (
    WithholdingTaxCertificateService,
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def commit(self) -> None:
        self.committed = True


class _FakePermissionService:
    def __init__(self, granted: set[str]) -> None:
        self._granted = granted

    def require_permission(self, code: str) -> None:
        if code not in self._granted:
            raise PermissionDeniedError(f"Missing permission: {code}")


def _build_certificate(**overrides) -> WithholdingTaxCertificate:
    base = WithholdingTaxCertificate(
        company_id=1,
        direction=WHT_DIRECTION_INBOUND,
        counterparty_kind=WHT_COUNTERPARTY_CUSTOMER,
        counterparty_name="Customer Co",
        tax_code_id=5,
        certificate_number="WHT-0001",
        certificate_date=date(2026, 3, 15),
        taxable_base=Decimal("1000.00"),
        tax_amount=Decimal("100.00"),
        status_code=WHT_STATUS_RECEIVED,
    )
    base.id = overrides.pop("id", 7)
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _build_service(
    *,
    granted: set[str] | None = None,
    certificate: WithholdingTaxCertificate | None = None,
    journal_entries: dict[int, object] | None = None,
    je_factory_wired: bool = True,
):
    if granted is None:
        granted = {
            WithholdingTaxCertificateService.PERMISSION_VIEW,
            WithholdingTaxCertificateService.PERMISSION_MANAGE,
        }
    uow = _FakeUnitOfWork()

    cert = certificate if certificate is not None else _build_certificate()

    repo = MagicMock(name="WithholdingTaxCertificateRepository")
    repo.get_by_id.side_effect = lambda cid, certid: (
        cert if cert.company_id == cid and cert.id == certid else None
    )
    repo.save.side_effect = lambda c: c

    company_repo = MagicMock(name="CompanyRepository")
    company_repo.get_by_id.return_value = SimpleNamespace(id=1, name="Acme")

    je_repo = MagicMock(name="JournalEntryRepository")
    journal_entries = journal_entries or {}
    je_repo.get_by_id.side_effect = lambda cid, jid: journal_entries.get(jid)

    je_factory = (lambda session: je_repo) if je_factory_wired else None

    service = WithholdingTaxCertificateService(
        unit_of_work_factory=lambda: uow,
        app_context=SimpleNamespace(current_user_id=42),
        certificate_repository_factory=lambda session: repo,
        company_repository_factory=lambda session: company_repo,
        permission_service=_FakePermissionService(granted),
        audit_service=None,
        journal_entry_repository_factory=je_factory,
    )
    return service, cert, je_repo, uow


def _je(jid: int, *, status: str = "POSTED", entry_number: str = "JE-0001"):
    return SimpleNamespace(
        id=jid,
        company_id=1,
        entry_number=entry_number,
        entry_date=date(2026, 3, 15),
        status_code=status,
        description="Supplier payment with WHT",
    )


class LinkWithholdingCertificateTests(unittest.TestCase):

    def test_link_to_posted_je_sets_source_document_and_commits(self) -> None:
        je = _je(99)
        service, cert, je_repo, uow = _build_service(
            journal_entries={99: je}
        )
        cmd = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=cert.id,
            journal_entry_id=99,
        )
        dto = service.link_to_journal_entry(1, cmd)
        self.assertEqual(dto.source_document_type, "journal_entry")
        self.assertEqual(dto.source_document_id, 99)
        self.assertTrue(uow.committed)

    def test_clearing_link_when_journal_entry_id_is_none(self) -> None:
        cert = _build_certificate(
            source_document_type="journal_entry",
            source_document_id=99,
        )
        service, _cert, _je_repo, _uow = _build_service(
            certificate=cert,
            journal_entries={},
        )
        cmd = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=cert.id,
            journal_entry_id=None,
        )
        dto = service.link_to_journal_entry(1, cmd)
        self.assertIsNone(dto.source_document_type)
        self.assertIsNone(dto.source_document_id)

    def test_link_rejects_voided_certificate(self) -> None:
        cert = _build_certificate(status_code=WHT_STATUS_VOIDED)
        service, _cert, _je_repo, _uow = _build_service(
            certificate=cert,
            journal_entries={99: _je(99)},
        )
        cmd = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=cert.id,
            journal_entry_id=99,
        )
        with self.assertRaises(ValidationError):
            service.link_to_journal_entry(1, cmd)

    def test_link_rejects_unknown_journal_entry(self) -> None:
        service, cert, _je_repo, _uow = _build_service(
            journal_entries={},
        )
        cmd = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=cert.id,
            journal_entry_id=12345,
        )
        with self.assertRaises(NotFoundError):
            service.link_to_journal_entry(1, cmd)

    def test_link_rejects_non_posted_journal_entry(self) -> None:
        je = _je(99, status="DRAFT")
        service, cert, _je_repo, _uow = _build_service(
            journal_entries={99: je},
        )
        cmd = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=cert.id,
            journal_entry_id=99,
        )
        with self.assertRaises(ValidationError):
            service.link_to_journal_entry(1, cmd)

    def test_link_requires_je_factory_when_setting_link(self) -> None:
        service, cert, _je_repo, _uow = _build_service(
            journal_entries={99: _je(99)},
            je_factory_wired=False,
        )
        cmd = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=cert.id,
            journal_entry_id=99,
        )
        with self.assertRaises(ValidationError):
            service.link_to_journal_entry(1, cmd)

    def test_clear_link_works_without_je_factory(self) -> None:
        cert = _build_certificate(
            source_document_type="journal_entry",
            source_document_id=99,
        )
        service, _cert, _je_repo, _uow = _build_service(
            certificate=cert,
            journal_entries={},
            je_factory_wired=False,
        )
        cmd = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=cert.id,
            journal_entry_id=None,
        )
        dto = service.link_to_journal_entry(1, cmd)
        self.assertIsNone(dto.source_document_id)

    def test_link_requires_manage_permission(self) -> None:
        service, cert, _je_repo, _uow = _build_service(
            granted={WithholdingTaxCertificateService.PERMISSION_VIEW},
            journal_entries={99: _je(99)},
        )
        cmd = LinkWithholdingCertificateToJournalEntryCommand(
            certificate_id=cert.id,
            journal_entry_id=99,
        )
        with self.assertRaises(PermissionDeniedError):
            service.link_to_journal_entry(1, cmd)


if __name__ == "__main__":
    unittest.main()
