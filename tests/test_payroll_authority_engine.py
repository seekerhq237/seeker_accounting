"""Integration tests for Phase 5 — Payroll authority registry & engine.

Covers:

* P5.S1 — :class:`PayrollAuthorityService` CRUD + mapping upsert/delete.
* P5.S3 — :class:`PayrollRemittanceEngine` period & explicit-runs flows.

Uses an in-memory SQLite session via :class:`SqlAlchemyUnitOfWork` and
stubbed permission/audit services. We do NOT post journal entries; we
seed PayrollRun + PayrollRunLine rows directly to mimic an approved run.
"""
from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db.base import Base
from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
import seeker_accounting.db.model_registry  # noqa: F401  (register all mappers)

from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.payroll.dto.payroll_authority_dto import (
    CreateComponentAuthorityMappingCommand,
    CreatePayrollAuthorityCommand,
    UpdatePayrollAuthorityCommand,
)
from seeker_accounting.modules.payroll.models.employee import Employee
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import (
    PayrollRunEmployee,
)
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine
from seeker_accounting.modules.payroll.repositories.payroll_authority_repository import (
    PayrollAuthorityRepository,
    PayrollComponentAuthorityMapRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.modules.payroll.services.payroll_authority_service import (
    PayrollAuthorityService,
)
from seeker_accounting.modules.payroll.services.payroll_remittance_engine import (
    PayrollRemittanceEngine,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


# ── Stubs ────────────────────────────────────────────────────────────


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


# ── Fixture ─────────────────────────────────────────────────────────


def _build_fixture() -> tuple[
    PayrollAuthorityService,
    PayrollRemittanceEngine,
    sessionmaker,
    int,
    dict[str, int],
]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF: sessionmaker = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session,
    )

    setup = SF()
    try:
        company = Company(
            legal_name="Test Co",
            display_name="Test Co",
            country_code="CM",
            base_currency_code="XAF",
        )
        setup.add(company)
        setup.flush()
        company_id = company.id

        cnps_emp = PayrollComponent(
            company_id=company_id,
            component_code="EMPLOYEE_CNPS",
            component_name="CNPS Pension (Employee)",
            component_type_code="deduction",
            calculation_method_code="rule_based",
            is_taxable=False,
            is_pensionable=False,
        )
        cnps_er = PayrollComponent(
            company_id=company_id,
            component_code="EMPLOYER_CNPS",
            component_name="CNPS Pension (Employer)",
            component_type_code="employer_contribution",
            calculation_method_code="rule_based",
            is_taxable=False,
            is_pensionable=False,
        )
        irpp = PayrollComponent(
            company_id=company_id,
            component_code="IRPP",
            component_name="IRPP Withholding",
            component_type_code="tax",
            calculation_method_code="rule_based",
            is_taxable=False,
            is_pensionable=False,
        )
        setup.add_all([cnps_emp, cnps_er, irpp])
        setup.flush()

        component_ids = {
            "EMPLOYEE_CNPS": cnps_emp.id,
            "EMPLOYER_CNPS": cnps_er.id,
            "IRPP": irpp.id,
        }

        emp = Employee(
            company_id=company_id,
            employee_number="EMP-001",
            display_name="Ada Lovelace",
            first_name="Ada",
            last_name="Lovelace",
            hire_date=date(2024, 1, 15),
            base_currency_code="XAF",
        )
        setup.add(emp)
        setup.flush()

        run = PayrollRun(
            company_id=company_id,
            run_reference="2024-03",
            run_label="March 2024",
            period_year=2024,
            period_month=3,
            status_code="approved",
            currency_code="XAF",
            run_date=date(2024, 3, 31),
        )
        setup.add(run)
        setup.flush()

        run_emp = PayrollRunEmployee(
            company_id=company_id,
            run_id=run.id,
            employee_id=emp.id,
            gross_earnings=Decimal("500000"),
            taxable_salary_base=Decimal("500000"),
            tdl_base=Decimal("500000"),
            cnps_contributory_base=Decimal("500000"),
            employer_cost_base=Decimal("500000"),
            net_payable=Decimal("400000"),
            total_earnings=Decimal("500000"),
            total_employee_deductions=Decimal("100000"),
            total_employer_contributions=Decimal("70000"),
            total_taxes=Decimal("50000"),
            status_code="included",
        )
        setup.add(run_emp)
        setup.flush()

        for cid, amount in (
            (cnps_emp.id, Decimal("21000")),
            (cnps_er.id, Decimal("21000")),
            (irpp.id, Decimal("50000")),
        ):
            setup.add(
                PayrollRunLine(
                    company_id=company_id,
                    run_id=run.id,
                    run_employee_id=run_emp.id,
                    employee_id=emp.id,
                    component_id=cid,
                    component_type_code="deduction",
                    calculation_basis=Decimal("500000"),
                    rate_applied=None,
                    component_amount=amount,
                )
            )
        setup.commit()
    finally:
        setup.close()

    uow_factory = create_unit_of_work_factory(SF)
    perm = _GrantAll()
    audit = _NoopAudit()
    authority_service = PayrollAuthorityService(
        unit_of_work_factory=uow_factory,
        authority_repository_factory=PayrollAuthorityRepository,
        map_repository_factory=PayrollComponentAuthorityMapRepository,
        component_repository_factory=PayrollComponentRepository,
        permission_service=perm,
        audit_service=audit,
    )
    engine_svc = PayrollRemittanceEngine(
        unit_of_work_factory=uow_factory,
        authority_repository_factory=PayrollAuthorityRepository,
        map_repository_factory=PayrollComponentAuthorityMapRepository,
        permission_service=perm,
    )
    return authority_service, engine_svc, SF, company_id, component_ids


# ── Tests ──────────────────────────────────────────────────────────


class PayrollAuthorityServiceTests(unittest.TestCase):
    def test_create_and_list_authority(self) -> None:
        svc, _, _, company_id, _ = _build_fixture()
        dto = svc.create_authority(
            company_id,
            CreatePayrollAuthorityCommand(code="CNPS", name="Caisse Nationale"),
        )
        self.assertEqual(dto.code, "CNPS")
        self.assertEqual(dto.filing_cadence_code, "monthly")
        self.assertTrue(dto.is_active)

        listed = svc.list_authorities(company_id)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].code, "CNPS")

    def test_duplicate_code_rejected(self) -> None:
        svc, _, _, company_id, _ = _build_fixture()
        svc.create_authority(
            company_id, CreatePayrollAuthorityCommand(code="DGI", name="Tax")
        )
        with self.assertRaises(ConflictError):
            svc.create_authority(
                company_id, CreatePayrollAuthorityCommand(code="DGI", name="Other")
            )

    def test_invalid_filing_cadence_rejected(self) -> None:
        svc, _, _, company_id, _ = _build_fixture()
        with self.assertRaises(ValidationError):
            svc.create_authority(
                company_id,
                CreatePayrollAuthorityCommand(
                    code="X", name="X", filing_cadence_code="biweekly",
                ),
            )

    def test_update_authority_records_changes(self) -> None:
        svc, _, _, company_id, _ = _build_fixture()
        a = svc.create_authority(
            company_id, CreatePayrollAuthorityCommand(code="DGI", name="Tax"),
        )
        updated = svc.update_authority(
            company_id,
            a.id,
            UpdatePayrollAuthorityCommand(name="DGI Cameroon", is_active=False),
        )
        self.assertEqual(updated.name, "DGI Cameroon")
        self.assertFalse(updated.is_active)

    def test_set_mapping_upsert(self) -> None:
        svc, _, _, company_id, components = _build_fixture()
        a = svc.create_authority(
            company_id, CreatePayrollAuthorityCommand(code="CNPS", name="CNPS")
        )
        m1 = svc.set_mapping(
            company_id,
            CreateComponentAuthorityMappingCommand(
                component_id=components["EMPLOYEE_CNPS"],
                authority_id=a.id,
                side="employee",
                line_kind="contribution",
                fraction=Decimal("1.0"),
            ),
        )
        # Upsert with different fraction → same id, updated fraction.
        m2 = svc.set_mapping(
            company_id,
            CreateComponentAuthorityMappingCommand(
                component_id=components["EMPLOYEE_CNPS"],
                authority_id=a.id,
                side="employee",
                fraction=Decimal("0.5"),
            ),
        )
        self.assertEqual(m1.id, m2.id)
        self.assertEqual(m2.fraction, Decimal("0.5"))

    def test_invalid_fraction_rejected(self) -> None:
        svc, _, _, company_id, components = _build_fixture()
        a = svc.create_authority(
            company_id, CreatePayrollAuthorityCommand(code="X", name="X")
        )
        with self.assertRaises(ValidationError):
            svc.set_mapping(
                company_id,
                CreateComponentAuthorityMappingCommand(
                    component_id=components["EMPLOYEE_CNPS"],
                    authority_id=a.id,
                    side="employee",
                    fraction=Decimal("1.5"),
                ),
            )


class PayrollRemittanceEngineTests(unittest.TestCase):
    def _setup_cnps_authority(self) -> tuple[
        PayrollAuthorityService,
        PayrollRemittanceEngine,
        int,
        int,
    ]:
        svc, engine, _, company_id, components = _build_fixture()
        a = svc.create_authority(
            company_id,
            CreatePayrollAuthorityCommand(code="CNPS", name="CNPS"),
        )
        for code, side in (("EMPLOYEE_CNPS", "employee"), ("EMPLOYER_CNPS", "employer")):
            svc.set_mapping(
                company_id,
                CreateComponentAuthorityMappingCommand(
                    component_id=components[code],
                    authority_id=a.id,
                    side=side,
                    line_kind="contribution",
                    fraction=Decimal("1.0"),
                ),
            )
        return svc, engine, company_id, a.id

    def test_estimate_for_period_aggregates_mapped_components(self) -> None:
        _svc, engine, company_id, authority_id = self._setup_cnps_authority()
        est = engine.estimate_for_period(
            company_id,
            authority_id=authority_id,
            period_year=2024,
            period_month=3,
        )
        self.assertEqual(est.authority_code, "CNPS")
        self.assertEqual(est.currency_code, "XAF")
        self.assertEqual(len(est.lines), 2)
        amounts = {ln.component_code: ln.amount for ln in est.lines}
        self.assertEqual(amounts["EMPLOYEE_CNPS"], Decimal("21000.0000"))
        self.assertEqual(amounts["EMPLOYER_CNPS"], Decimal("21000.0000"))
        self.assertEqual(est.total_amount, Decimal("42000.0000"))
        self.assertEqual(len(est.payroll_run_ids), 1)

    def test_estimate_with_partial_fraction(self) -> None:
        svc, engine, _, company_id, components = _build_fixture()
        a = svc.create_authority(
            company_id, CreatePayrollAuthorityCommand(code="CNPS", name="CNPS")
        )
        svc.set_mapping(
            company_id,
            CreateComponentAuthorityMappingCommand(
                component_id=components["EMPLOYEE_CNPS"],
                authority_id=a.id,
                side="employee",
                fraction=Decimal("0.5"),
            ),
        )
        est = engine.estimate_for_period(
            company_id,
            authority_id=a.id,
            period_year=2024,
            period_month=3,
        )
        self.assertEqual(len(est.lines), 1)
        self.assertEqual(est.lines[0].amount, Decimal("10500.0000"))

    def test_estimate_no_mappings_warns(self) -> None:
        svc, engine, _, company_id, _ = _build_fixture()
        a = svc.create_authority(
            company_id, CreatePayrollAuthorityCommand(code="X", name="X")
        )
        est = engine.estimate_for_period(
            company_id,
            authority_id=a.id,
            period_year=2024,
            period_month=3,
        )
        self.assertEqual(est.lines, ())
        self.assertTrue(any("No component" in w for w in est.warnings))

    def test_estimate_no_qualifying_runs(self) -> None:
        _svc, engine, company_id, authority_id = self._setup_cnps_authority()
        est = engine.estimate_for_period(
            company_id,
            authority_id=authority_id,
            period_year=2024,
            period_month=4,  # nothing seeded here
        )
        self.assertEqual(est.lines, ())
        self.assertEqual(est.payroll_run_ids, ())
        self.assertTrue(any("No approved or posted" in w for w in est.warnings))

    def test_estimate_invalid_month(self) -> None:
        _svc, engine, company_id, authority_id = self._setup_cnps_authority()
        with self.assertRaises(ValidationError):
            engine.estimate_for_period(
                company_id,
                authority_id=authority_id,
                period_year=2024,
                period_month=0,
            )

    def test_estimate_unknown_authority(self) -> None:
        _svc, engine, company_id, _ = self._setup_cnps_authority()
        with self.assertRaises(NotFoundError):
            engine.estimate_for_period(
                company_id,
                authority_id=99999,
                period_year=2024,
                period_month=3,
            )


if __name__ == "__main__":
    unittest.main()
