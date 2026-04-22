"""PayrollRunService — manage payroll runs and trigger calculation.

Responsibilities:
  - Create/manage payroll run headers
  - Orchestrate per-employee calculation via PayrollCalculationService
  - Write results to payroll_run_employees and payroll_run_lines
  - Enforce run lifecycle state transitions
  - Approve and void runs

Does NOT post to journals or general ledger.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreatePayrollRunCommand,
    PayrollRunDetailDTO,
    PayrollRunEmployeeDetailDTO,
    PayrollRunEmployeeListItemDTO,
    PayrollRunLineDTO,
    PayrollRunListItemDTO,
)
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine
from seeker_accounting.modules.payroll.repositories.compensation_profile_repository import (
    CompensationProfileRepository,
)
from seeker_accounting.modules.payroll.repositories.component_assignment_repository import (
    ComponentAssignmentRepository,
)
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.modules.payroll.repositories.payroll_input_batch_repository import (
    PayrollInputBatchRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import (
    PayrollRuleSetRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunEmployeeRepository,
    PayrollRunRepository,
)
from seeker_accounting.modules.payroll.payroll_permissions import (
    PAYROLL_RUN_APPROVE,
    PAYROLL_RUN_CALCULATE,
    PAYROLL_RUN_CREATE,
)
from seeker_accounting.modules.payroll.services.payroll_calculation_service import (
    PayrollCalculationService,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService

PayrollRunRepositoryFactory = Callable[[Session], PayrollRunRepository]
PayrollRunEmployeeRepositoryFactory = Callable[[Session], PayrollRunEmployeeRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
CompensationProfileRepositoryFactory = Callable[[Session], CompensationProfileRepository]
ComponentAssignmentRepositoryFactory = Callable[[Session], ComponentAssignmentRepository]
PayrollInputBatchRepositoryFactory = Callable[[Session], PayrollInputBatchRepository]
PayrollRuleSetRepositoryFactory = Callable[[Session], PayrollRuleSetRepository]

_RUN_DOC_TYPE = "payroll_run"

_CALENDAR_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


class PayrollRunService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        run_repository_factory: PayrollRunRepositoryFactory,
        run_employee_repository_factory: PayrollRunEmployeeRepositoryFactory,
        employee_repository_factory: EmployeeRepositoryFactory,
        profile_repository_factory: CompensationProfileRepositoryFactory,
        assignment_repository_factory: ComponentAssignmentRepositoryFactory,
        input_batch_repository_factory: PayrollInputBatchRepositoryFactory,
        rule_set_repository_factory: PayrollRuleSetRepositoryFactory,
        calculation_service: PayrollCalculationService,
        numbering_service: NumberingService,
        permission_service: PermissionService,
        audit_service: AuditService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._run_repo_factory = run_repository_factory
        self._run_employee_repo_factory = run_employee_repository_factory
        self._employee_repo_factory = employee_repository_factory
        self._profile_repo_factory = profile_repository_factory
        self._assignment_repo_factory = assignment_repository_factory
        self._input_batch_repo_factory = input_batch_repository_factory
        self._rule_set_repo_factory = rule_set_repository_factory
        self._calc_service = calculation_service
        self._numbering_service = numbering_service
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_runs(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[PayrollRunListItemDTO]:
        with self._uow_factory() as uow:
            repo = self._run_repo_factory(uow.session)
            runs = repo.list_by_company(company_id, status_code=status_code)
            run_emp_repo = self._run_employee_repo_factory(uow.session)
            result = []
            for r in runs:
                employees = run_emp_repo.list_by_run(company_id, r.id)
                included = [e for e in employees if e.status_code == "included"]
                total_net = sum(Decimal(str(e.net_payable)) for e in included)
                total_gross = sum(Decimal(str(e.gross_earnings)) for e in included)
                result.append(
                    PayrollRunListItemDTO(
                        id=r.id,
                        company_id=r.company_id,
                        run_reference=r.run_reference,
                        run_label=r.run_label,
                        period_year=r.period_year,
                        period_month=r.period_month,
                        status_code=r.status_code,
                        currency_code=r.currency_code,
                        run_date=r.run_date,
                        payment_date=r.payment_date,
                        employee_count=len(included),
                        total_net_payable=total_net,
                        total_gross_earnings=total_gross,
                        posted_journal_entry_id=r.posted_journal_entry_id,
                    )
                )
            return result

    def get_run(self, company_id: int, run_id: int) -> PayrollRunDetailDTO:
        with self._uow_factory() as uow:
            repo = self._run_repo_factory(uow.session)
            run = repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            return self._to_run_dto(run)

    def list_run_employees(
        self, company_id: int, run_id: int
    ) -> list[PayrollRunEmployeeListItemDTO]:
        with self._uow_factory() as uow:
            self._assert_run_exists(uow.session, company_id, run_id)
            repo = self._run_employee_repo_factory(uow.session)
            rows = repo.list_by_run(company_id, run_id)
            return [self._to_run_employee_list_dto(r) for r in rows]

    def get_run_employee_detail(
        self, company_id: int, run_employee_id: int
    ) -> PayrollRunEmployeeDetailDTO:
        with self._uow_factory() as uow:
            repo = self._run_employee_repo_factory(uow.session)
            row = repo.get_by_id(company_id, run_employee_id)
            if row is None:
                raise NotFoundError("Employee payroll detail not found.")
            run = self._run_repo_factory(uow.session).get_by_id(company_id, row.run_id)
            return self._to_run_employee_detail_dto(row, run)

    # ── Commands ──────────────────────────────────────────────────────────────

    def create_run(
        self, company_id: int, cmd: CreatePayrollRunCommand
    ) -> PayrollRunDetailDTO:
        self._permission_service.require_permission(PAYROLL_RUN_CREATE)
        self._validate_period(cmd.period_year, cmd.period_month)
        with self._uow_factory() as uow:
            repo = self._run_repo_factory(uow.session)
            existing = repo.get_by_period(company_id, cmd.period_year, cmd.period_month)
            if existing is not None:
                raise ConflictError(
                    f"A payroll run already exists for "
                    f"{_CALENDAR_MONTHS[cmd.period_month]} {cmd.period_year}."
                )
            ref = self._numbering_service.issue_next_number(
                uow.session, company_id, _RUN_DOC_TYPE
            )
            run = PayrollRun(
                company_id=company_id,
                run_reference=ref,
                run_label=cmd.run_label or f"{_CALENDAR_MONTHS[cmd.period_month]} {cmd.period_year} Payroll",
                period_year=cmd.period_year,
                period_month=cmd.period_month,
                status_code="draft",
                currency_code=cmd.currency_code,
                run_date=cmd.run_date,
                payment_date=cmd.payment_date,
                notes=cmd.notes,
            )
            repo.save(run)
            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_CREATED",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=f"Created payroll run '{run.run_reference}'.",
                    detail_json=json.dumps({
                        "run_reference": run.run_reference,
                        "period_year": run.period_year,
                        "period_month": run.period_month,
                    }),
                ),
            )
            uow.commit()
            uow.session.refresh(run)
            return self._to_run_dto(run)

    def calculate_run(self, company_id: int, run_id: int) -> PayrollRunDetailDTO:
        """Trigger calculation engines for all active employees in the period."""
        self._permission_service.require_permission(PAYROLL_RUN_CALCULATE)
        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            if run.status_code == "posted":
                raise ValidationError(
                    "Posted payroll runs cannot be recalculated. "
                    "Payroll accounting truth is locked once the run is posted to the GL."
                )
            if run.status_code not in ("draft", "calculated"):
                raise ValidationError(
                    "Only draft or previously calculated runs can be recalculated."
                )

            period_date = date(run.period_year, run.period_month, 1)

            # Clear previous calculation results
            run_emp_repo = self._run_employee_repo_factory(uow.session)
            run_emp_repo.delete_all_for_run(run_id)
            uow.session.flush()

            # Load all active employees
            emp_repo = self._employee_repo_factory(uow.session)
            employees = emp_repo.list_by_company(company_id, active_only=True)

            # Load approved input batches for this period
            input_batch_repo = self._input_batch_repo_factory(uow.session)
            input_batches = input_batch_repo.get_approved_for_period(
                company_id, run.period_year, run.period_month
            )

            # Load all active rule sets for the company
            rule_set_repo = self._rule_set_repo_factory(uow.session)
            rule_sets = rule_set_repo.list_by_company(company_id, active_only=True)

            profile_repo = self._profile_repo_factory(uow.session)
            assignment_repo = self._assignment_repo_factory(uow.session)
            included_count = 0
            error_count = 0

            for emp in employees:
                profile = profile_repo.get_active_for_period(
                    company_id, emp.id, period_date
                )
                if profile is None:
                    # No profile — record as error row
                    err_row = PayrollRunEmployee(
                        company_id=company_id,
                        run_id=run_id,
                        employee_id=emp.id,
                        status_code="error",
                        calculation_notes="No active compensation profile for this period.",
                    )
                    run_emp_repo.save(err_row)
                    error_count += 1
                    continue

                assignments = assignment_repo.get_active_for_period(
                    company_id, emp.id, period_date
                )

                calc_result = self._calc_service.calculate(
                    profile=profile,
                    assignments=assignments,
                    input_batches=input_batches,
                    rule_sets=rule_sets,
                    period_year=run.period_year,
                    period_month=run.period_month,
                )

                if calc_result.error_message:
                    err_row = PayrollRunEmployee(
                        company_id=company_id,
                        run_id=run_id,
                        employee_id=emp.id,
                        status_code="error",
                        calculation_notes=calc_result.error_message,
                    )
                    run_emp_repo.save(err_row)
                    error_count += 1
                    continue

                run_emp = PayrollRunEmployee(
                    company_id=company_id,
                    run_id=run_id,
                    employee_id=emp.id,
                    gross_earnings=calc_result.gross_earnings,
                    taxable_salary_base=calc_result.taxable_salary_base,
                    tdl_base=calc_result.tdl_base,
                    cnps_contributory_base=calc_result.cnps_contributory_base,
                    employer_cost_base=calc_result.employer_cost_base,
                    net_payable=calc_result.net_payable,
                    total_earnings=calc_result.total_earnings,
                    total_employee_deductions=calc_result.total_employee_deductions,
                    total_employer_contributions=calc_result.total_employer_contributions,
                    total_taxes=calc_result.total_taxes,
                    status_code="included",
                )
                run_emp_repo.save(run_emp)
                uow.session.flush()
                included_count += 1

                # Write individual lines
                for line in calc_result.lines:
                    run_line = PayrollRunLine(
                        company_id=company_id,
                        run_id=run_id,
                        run_employee_id=run_emp.id,
                        employee_id=emp.id,
                        component_id=line.component_id,
                        component_type_code=line.component_type_code,
                        calculation_basis=line.calculation_basis,
                        rate_applied=line.rate_applied,
                        component_amount=line.component_amount,
                    )
                    uow.session.add(run_line)

            run.status_code = "calculated"
            run.calculated_at = datetime.now(timezone.utc)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_CALCULATED",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=f"Calculated payroll run '{run.run_reference}'.",
                    detail_json=json.dumps(
                        {
                            "run_reference": run.run_reference,
                            "period_year": run.period_year,
                            "period_month": run.period_month,
                            "included_employee_count": included_count,
                            "error_employee_count": error_count,
                        }
                    ),
                ),
            )
            uow.commit()
            uow.session.refresh(run)
            return self._to_run_dto(run)

    def approve_run(self, company_id: int, run_id: int) -> None:
        self._permission_service.require_permission(PAYROLL_RUN_APPROVE)
        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            if run.status_code != "calculated":
                raise ValidationError("Only calculated runs can be approved.")
            run.status_code = "approved"
            run.approved_at = datetime.now(timezone.utc)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_APPROVED",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=f"Approved payroll run '{run.run_reference}'.",
                ),
            )
            uow.commit()

    def void_run(self, company_id: int, run_id: int) -> None:
        self._permission_service.require_permission(PAYROLL_RUN_CREATE)
        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            if run.status_code == "voided":
                raise ValidationError("Run is already voided.")
            if run.status_code == "posted":
                raise ValidationError(
                    "Posted payroll runs cannot be voided. "
                    "The payroll journal entry is the accounting record of this run."
                )
            if run.status_code == "approved":
                raise ValidationError(
                    "Approved runs cannot be voided. Contact your administrator."
                )
            run.status_code = "voided"
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_VOIDED",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=f"Voided payroll run '{run.run_reference}'.",
                ),
            )
            uow.commit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _assert_run_exists(self, session: Session, company_id: int, run_id: int) -> None:
        repo = self._run_repo_factory(session)
        if repo.get_by_id(company_id, run_id) is None:
            raise NotFoundError("Payroll run not found.")

    @staticmethod
    def _validate_period(year: int, month: int) -> None:
        if not (2000 <= year <= 2100):
            raise ValidationError("Period year must be between 2000 and 2100.")
        if not (1 <= month <= 12):
            raise ValidationError("Period month must be between 1 and 12.")

    @staticmethod
    def _to_run_dto(r: PayrollRun) -> PayrollRunDetailDTO:
        return PayrollRunDetailDTO(
            id=r.id,
            company_id=r.company_id,
            run_reference=r.run_reference,
            run_label=r.run_label,
            period_year=r.period_year,
            period_month=r.period_month,
            status_code=r.status_code,
            currency_code=r.currency_code,
            run_date=r.run_date,
            payment_date=r.payment_date,
            notes=r.notes,
            calculated_at=r.calculated_at,
            approved_at=r.approved_at,
            posted_at=r.posted_at,
            posted_by_user_id=r.posted_by_user_id,
            posted_journal_entry_id=r.posted_journal_entry_id,
        )

    @staticmethod
    def _to_run_employee_list_dto(r: PayrollRunEmployee) -> PayrollRunEmployeeListItemDTO:
        emp = r.employee
        return PayrollRunEmployeeListItemDTO(
            id=r.id,
            run_id=r.run_id,
            employee_id=r.employee_id,
            employee_number=emp.employee_number if emp else "",
            employee_display_name=emp.display_name if emp else "",
            gross_earnings=Decimal(str(r.gross_earnings)),
            total_employee_deductions=Decimal(str(r.total_employee_deductions)),
            total_taxes=Decimal(str(r.total_taxes)),
            net_payable=Decimal(str(r.net_payable)),
            employer_cost_base=Decimal(str(r.employer_cost_base)),
            status_code=r.status_code,
        )

    @staticmethod
    def _to_run_employee_detail_dto(
        r: PayrollRunEmployee, run: PayrollRun | None
    ) -> PayrollRunEmployeeDetailDTO:
        emp = r.employee
        lines = [
            PayrollRunLineDTO(
                id=ln.id,
                component_id=ln.component_id,
                component_name=ln.component.component_name if ln.component else "",
                component_code=ln.component.component_code if ln.component else "",
                component_type_code=ln.component_type_code,
                calculation_basis=Decimal(str(ln.calculation_basis)),
                rate_applied=Decimal(str(ln.rate_applied)) if ln.rate_applied is not None else None,
                component_amount=Decimal(str(ln.component_amount)),
            )
            for ln in (r.lines or [])
        ]
        return PayrollRunEmployeeDetailDTO(
            id=r.id,
            run_id=r.run_id,
            run_reference=run.run_reference if run else "",
            period_year=run.period_year if run else r.run_id,
            period_month=run.period_month if run else 0,
            employee_id=r.employee_id,
            employee_number=emp.employee_number if emp else "",
            employee_display_name=emp.display_name if emp else "",
            gross_earnings=Decimal(str(r.gross_earnings)),
            taxable_salary_base=Decimal(str(r.taxable_salary_base)),
            tdl_base=Decimal(str(r.tdl_base)),
            cnps_contributory_base=Decimal(str(r.cnps_contributory_base)),
            employer_cost_base=Decimal(str(r.employer_cost_base)),
            net_payable=Decimal(str(r.net_payable)),
            total_earnings=Decimal(str(r.total_earnings)),
            total_employee_deductions=Decimal(str(r.total_employee_deductions)),
            total_employer_contributions=Decimal(str(r.total_employer_contributions)),
            total_taxes=Decimal(str(r.total_taxes)),
            status_code=r.status_code,
            calculation_notes=r.calculation_notes,
            lines=lines,
        )
