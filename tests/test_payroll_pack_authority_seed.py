"""Integration test — Phase 5 / P5.S2.

Pack-driven authority seed:

* Apply Cameroon pack to a fresh company → CNPS, DGI, FNE, CFC authorities present.
* Component → authority mappings present (CNPS_EMPLOYEE → CNPS, IRPP → DGI, ...).
* A second apply is idempotent (no duplicate authorities or mappings).
"""
from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db.base import Base
from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
import seeker_accounting.db.model_registry  # noqa: F401  (register all mappers)

from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.companies.repositories.company_repository import (
    CompanyRepository,
)
from seeker_accounting.modules.payroll.repositories.company_payroll_setting_repository import (
    CompanyPayrollSettingRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_authority_repository import (
    PayrollAuthorityRepository,
    PayrollComponentAuthorityMapRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import (
    PayrollRuleSetRepository,
)
from seeker_accounting.modules.payroll.services.payroll_statutory_pack_service import (
    PayrollStatutoryPackService,
)
from seeker_accounting.modules.payroll.statutory_packs import cameroon_default_pack as _cmr


class _GrantAll:
    def require_permission(self, code: str) -> None:
        return None

    def has_permission(self, code: str) -> bool:
        return True


class _NoopAudit:
    def __init__(self) -> None:
        self.events: list[str] = []

    def record_event_in_session(self, session, company_id, command):  # type: ignore[no-untyped-def]
        self.events.append(command.event_type_code)


def _build_service() -> tuple[PayrollStatutoryPackService, sessionmaker, int]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF: sessionmaker = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session,
    )

    setup = SF()
    try:
        company = Company(
            legal_name="Acme CM",
            display_name="Acme CM",
            country_code="CM",
            base_currency_code="XAF",
        )
        setup.add(company)
        setup.flush()
        company_id = company.id
        setup.commit()
    finally:
        setup.close()

    uow_factory = create_unit_of_work_factory(SF)
    service = PayrollStatutoryPackService(
        unit_of_work_factory=uow_factory,
        company_repository_factory=CompanyRepository,
        settings_repository_factory=CompanyPayrollSettingRepository,
        component_repository_factory=PayrollComponentRepository,
        rule_set_repository_factory=PayrollRuleSetRepository,
        permission_service=_GrantAll(),
        audit_service=_NoopAudit(),
        authority_repository_factory=PayrollAuthorityRepository,
        component_authority_map_repository_factory=PayrollComponentAuthorityMapRepository,
    )
    return service, SF, company_id


class CameroonPackAuthoritySeedTests(unittest.TestCase):
    def test_apply_creates_required_authorities(self) -> None:
        service, SF, company_id = _build_service()

        result = service.apply_pack(company_id, _cmr.PACK_CODE)

        self.assertEqual(result.authorities_created, len(_cmr.AUTHORITY_SEEDS))
        self.assertEqual(result.authorities_skipped, 0)
        self.assertGreater(result.mappings_created, 0)

        with SF() as session:
            repo = PayrollAuthorityRepository(session)
            authorities = repo.list_by_company(company_id)
            codes = {a.code for a in authorities}
            for required in ("CNPS", "DGI", "FNE", "CFC"):
                self.assertIn(required, codes, f"Missing required authority {required}")

    def test_apply_creates_expected_mappings(self) -> None:
        service, SF, company_id = _build_service()

        service.apply_pack(company_id, _cmr.PACK_CODE)

        with SF() as session:
            map_repo = PayrollComponentAuthorityMapRepository(session)
            mappings = map_repo.list_by_company(company_id)
            keys = {
                (m.component.component_code, m.authority.code, m.side)
                for m in mappings
            }
            # Spot-check key mappings from the manifest.
            self.assertIn(("EMPLOYEE_CNPS", "CNPS", "employee"), keys)
            self.assertIn(("EMPLOYER_CNPS", "CNPS", "employer"), keys)
            self.assertIn(("IRPP", "DGI", "employee"), keys)
            self.assertIn(("CAC", "DGI", "employee"), keys)
            self.assertIn(("FNE_EMPLOYEE", "FNE", "employee"), keys)
            self.assertIn(("FNE", "FNE", "employer"), keys)
            self.assertIn(("CFC_HLF", "CFC", "employee"), keys)

    def test_apply_is_idempotent(self) -> None:
        service, SF, company_id = _build_service()

        first = service.apply_pack(company_id, _cmr.PACK_CODE)
        second = service.apply_pack(company_id, _cmr.PACK_CODE)

        # First run: everything created.
        self.assertGreater(first.authorities_created, 0)
        self.assertGreater(first.mappings_created, 0)
        # Second run: nothing new, all skipped.
        self.assertEqual(second.authorities_created, 0)
        self.assertEqual(second.authorities_skipped, first.authorities_created)
        self.assertEqual(second.mappings_created, 0)
        self.assertEqual(second.mappings_skipped, first.mappings_created)

        with SF() as session:
            repo = PayrollAuthorityRepository(session)
            self.assertEqual(
                len(repo.list_by_company(company_id)),
                first.authorities_created,
            )
            map_repo = PayrollComponentAuthorityMapRepository(session)
            self.assertEqual(
                len(map_repo.list_by_company(company_id)),
                first.mappings_created,
            )


if __name__ == "__main__":
    unittest.main()
