"""Integration test — Phase 5 / P5.S5 statutory return pre-fill.

Validates that the engine's pre-fill payload:

* Builds one box per active mapping that has source run lines.
* Each box carries the originating ``PayrollRunLine`` ids
  (auditor-traceable from box → source line → journal line via run).
* Total amount matches the sum of box amounts.
"""
from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from seeker_accounting.db.base import Base
from seeker_accounting.db.unit_of_work import create_unit_of_work_factory
import seeker_accounting.db.model_registry  # noqa: F401  (register all mappers)

from seeker_accounting.modules.companies.models.company import Company
from seeker_accounting.modules.payroll.dto.payroll_authority_dto import (
    CreateComponentAuthorityMappingCommand,
    CreatePayrollAuthorityCommand,
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


class _GrantAll:
    def require_permission(self, code: str) -> None:
        return None


class _NoopAudit:
    def record_event_in_session(self, session, company_id, command):  # type: ignore[no-untyped-def]
        return None


def _build() -> tuple[
    PayrollAuthorityService, PayrollRemittanceEngine, sessionmaker, int, dict[str, int]
]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    SF: sessionmaker = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session,
    )

    s = SF()
    try:
        company = Company(
            legal_name="ReturnCo", display_name="ReturnCo",
            country_code="CM", base_currency_code="XAF",
        )
        s.add(company)
        s.flush()
        cid = company.id

        cnps_emp = PayrollComponent(
            company_id=cid, component_code="EMPLOYEE_CNPS",
            component_name="CNPS Pension (Employee)",
            component_type_code="deduction",
            calculation_method_code="rule_based",
            is_taxable=False, is_pensionable=False,
        )
        irpp = PayrollComponent(
            company_id=cid, component_code="IRPP",
            component_name="IRPP Withholding",
            component_type_code="tax",
            calculation_method_code="rule_based",
            is_taxable=False, is_pensionable=False,
        )
        s.add_all([cnps_emp, irpp])
        s.flush()

        emp = Employee(
            company_id=cid, employee_number="E1",
            display_name="Alice", first_name="Alice", last_name="A",
            hire_date=date(2024, 1, 1),
            base_currency_code="XAF",
        )
        s.add(emp)
        s.flush()

        run = PayrollRun(
            company_id=cid, run_reference="2024-04",
            run_label="April 2024", period_year=2024, period_month=4,
            status_code="approved", currency_code="XAF",
            run_date=date(2024, 4, 30),
        )
        s.add(run)
        s.flush()

        re = PayrollRunEmployee(
            company_id=cid, run_id=run.id, employee_id=emp.id,
            gross_earnings=Decimal("400000"),
            taxable_salary_base=Decimal("400000"),
            tdl_base=Decimal("400000"),
            cnps_contributory_base=Decimal("400000"),
            employer_cost_base=Decimal("400000"),
            net_payable=Decimal("320000"),
            total_earnings=Decimal("400000"),
            total_employee_deductions=Decimal("80000"),
            total_employer_contributions=Decimal("0"),
            total_taxes=Decimal("40000"),
            status_code="included",
        )
        s.add(re)
        s.flush()

        # Two run-lines for CNPS_EMP (so we can assert multiple source ids
        # are aggregated into one estimate row).
        for cid_, amount in (
            (cnps_emp.id, Decimal("10000")),
            (cnps_emp.id, Decimal("6800")),
            (irpp.id, Decimal("40000")),
        ):
            s.add(
                PayrollRunLine(
                    company_id=cid, run_id=run.id, run_employee_id=re.id,
                    employee_id=emp.id, component_id=cid_,
                    component_type_code="deduction",
                    calculation_basis=Decimal("400000"),
                    rate_applied=None, component_amount=amount,
                )
            )
        s.commit()
        comp_ids = {"EMPLOYEE_CNPS": cnps_emp.id, "IRPP": irpp.id}
    finally:
        s.close()

    uow_factory = create_unit_of_work_factory(SF)
    perm = _GrantAll()
    audit = _NoopAudit()
    auth_svc = PayrollAuthorityService(
        unit_of_work_factory=uow_factory,
        authority_repository_factory=PayrollAuthorityRepository,
        map_repository_factory=PayrollComponentAuthorityMapRepository,
        component_repository_factory=PayrollComponentRepository,
        permission_service=perm,
        audit_service=audit,
    )
    eng = PayrollRemittanceEngine(
        unit_of_work_factory=uow_factory,
        authority_repository_factory=PayrollAuthorityRepository,
        map_repository_factory=PayrollComponentAuthorityMapRepository,
        permission_service=perm,
    )
    return auth_svc, eng, SF, cid, comp_ids


class StatutoryReturnPrefillTests(unittest.TestCase):
    def test_prefill_carries_source_run_line_ids(self) -> None:
        auth_svc, engine, SF, company_id, comp_ids = _build()

        # Register two authorities + map components to them.
        cnps = auth_svc.create_authority(
            company_id,
            CreatePayrollAuthorityCommand(
                code="CNPS", name="Caisse Nationale",
                jurisdiction_code="CM", filing_cadence_code="monthly",
                deadline_day=15,
            ),
        )
        dgi = auth_svc.create_authority(
            company_id,
            CreatePayrollAuthorityCommand(
                code="DGI", name="Direction Gen Impots",
                jurisdiction_code="CM", filing_cadence_code="monthly",
                deadline_day=15,
            ),
        )
        auth_svc.set_mapping(
            company_id,
            CreateComponentAuthorityMappingCommand(
                component_id=comp_ids["EMPLOYEE_CNPS"],
                authority_id=cnps.id,
                side="employee",
                line_kind="contribution",
                fraction=Decimal("1.0"),
            ),
        )
        auth_svc.set_mapping(
            company_id,
            CreateComponentAuthorityMappingCommand(
                component_id=comp_ids["IRPP"],
                authority_id=dgi.id,
                side="employee",
                line_kind="withholding",
                fraction=Decimal("1.0"),
            ),
        )

        # Pre-fill CNPS return for April 2024.
        prefill = engine.get_statutory_return_prefill(
            company_id, authority_id=cnps.id,
            period_year=2024, period_month=4,
        )
        self.assertEqual(prefill.authority_code, "CNPS")
        self.assertEqual(len(prefill.boxes), 1)
        box = prefill.boxes[0]
        self.assertEqual(box.component_code, "EMPLOYEE_CNPS")
        self.assertEqual(box.amount, Decimal("16800.0000"))
        # Two run-lines fed this box → trace must contain both ids.
        self.assertEqual(len(box.source_run_line_ids), 2)

        # Cross-validate that the source ids point at real PayrollRunLine
        # rows for the EMPLOYEE_CNPS component.
        with SF() as session:
            rows = session.scalars(
                select(PayrollRunLine).where(
                    PayrollRunLine.id.in_(box.source_run_line_ids)
                )
            ).all()
            self.assertEqual(len(rows), 2)
            self.assertTrue(
                all(r.component_id == comp_ids["EMPLOYEE_CNPS"] for r in rows)
            )
            self.assertEqual(
                sum((Decimal(r.component_amount) for r in rows), Decimal("0")),
                Decimal("16800"),
            )

    def test_prefill_for_authority_with_no_runs(self) -> None:
        auth_svc, engine, _SF, company_id, _comp_ids = _build()
        empty = auth_svc.create_authority(
            company_id,
            CreatePayrollAuthorityCommand(
                code="FNE", name="Fonds National Emploi",
                jurisdiction_code="CM", filing_cadence_code="monthly",
                deadline_day=15,
            ),
        )

        prefill = engine.get_statutory_return_prefill(
            company_id, authority_id=empty.id,
            period_year=2024, period_month=4,
        )
        # No mappings → engine returns empty boxes + a warning.
        self.assertEqual(prefill.boxes, ())
        self.assertEqual(prefill.total_amount, Decimal("0"))
        self.assertTrue(prefill.warnings)


if __name__ == "__main__":
    unittest.main()
