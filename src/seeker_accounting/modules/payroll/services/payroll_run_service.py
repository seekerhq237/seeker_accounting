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
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.payroll_calculation_dto import (
    CreateOffCyclePayrollRunCommand,
    CreatePayrollRunCommand,
    PayrollRunDetailDTO,
    PayrollRunEmployeeDetailDTO,
    PayrollRunEmployeeListItemDTO,
    PayrollRunLineDTO,
    PayrollRunListItemDTO,
)
from seeker_accounting.modules.payroll.engines.engine_types import (
    EmployeeCalculationResult,
    EngineLineResult,
)
from seeker_accounting.modules.payroll.models.payroll_calculation_trace import (
    PayrollCalculationTrace,
)
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine
from seeker_accounting.modules.payroll.repositories.company_payroll_setting_repository import (
    CompanyPayrollSettingRepository,
)
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
from seeker_accounting.modules.payroll.repositories.employee_payroll_correction_repository import (
    EmployeePayrollCorrectionRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_calculation_trace_repository import (
    PayrollCalculationTraceRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunEmployeeRepository,
    PayrollRunRepository,
)
from seeker_accounting.modules.payroll.payroll_permissions import (
    PAYROLL_RUN_APPROVE,
    PAYROLL_RUN_CALCULATE,
    PAYROLL_RUN_CREATE,
    PAYROLL_RUN_SEND_BACK,
    PAYROLL_RUN_SUBMIT,
)
from seeker_accounting.modules.payroll.services.payroll_calculation_service import (
    PayrollCalculationService,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError
from seeker_accounting.platform.numbering.numbering_service import NumberingService
from seeker_accounting.shared.services.telemetry_service import TelemetryService

PayrollRunRepositoryFactory = Callable[[Session], PayrollRunRepository]
PayrollRunEmployeeRepositoryFactory = Callable[[Session], PayrollRunEmployeeRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
CompensationProfileRepositoryFactory = Callable[[Session], CompensationProfileRepository]
ComponentAssignmentRepositoryFactory = Callable[[Session], ComponentAssignmentRepository]
PayrollInputBatchRepositoryFactory = Callable[[Session], PayrollInputBatchRepository]
PayrollRuleSetRepositoryFactory = Callable[[Session], PayrollRuleSetRepository]
CompanyPayrollSettingRepositoryFactory = Callable[[Session], CompanyPayrollSettingRepository]
PayrollCalculationTraceRepositoryFactory = Callable[[Session], PayrollCalculationTraceRepository]
EmployeePayrollCorrectionRepositoryFactory = Callable[[Session], EmployeePayrollCorrectionRepository]

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
        setting_repository_factory: CompanyPayrollSettingRepositoryFactory | None = None,
        trace_repository_factory: PayrollCalculationTraceRepositoryFactory | None = None,
        correction_repository_factory: EmployeePayrollCorrectionRepositoryFactory | None = None,
        telemetry_service: TelemetryService | None = None,
        app_context: object | None = None,
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
        self._setting_repo_factory = setting_repository_factory
        self._trace_repo_factory = trace_repository_factory
        self._correction_repo_factory = correction_repository_factory
        self._telemetry = telemetry_service
        self._app_context = app_context

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_runs(
        self,
        company_id: int,
        status_code: str | None = None,
    ) -> list[PayrollRunListItemDTO]:
        with self._uow_factory() as uow:
            repo = self._run_repo_factory(uow.session)
            runs = repo.list_by_company(company_id, status_code=status_code)
            result = []
            for r in runs:
                included = [e for e in r.employees if e.status_code == "included"]
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
                        run_type_code=r.run_type_code,
                        run_sequence=r.run_sequence,
                        off_cycle_reason_code=r.off_cycle_reason_code,
                        source_run_id=r.source_run_id,
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

    def list_employee_run_history(
        self,
        company_id: int,
        employee_id: int,
        limit: int = 20,
    ) -> list[tuple[PayrollRunListItemDTO, PayrollRunEmployeeListItemDTO]]:
        """Return run + employee-result pairs for a single employee, newest first.

        Uses a single JOIN query instead of N+1 list_runs + list_run_employees calls.
        """
        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            pairs = run_repo.list_runs_for_employee(company_id, employee_id, limit=limit)
            result = []
            for run, emp_row in pairs:
                run_dto = PayrollRunListItemDTO(
                    id=run.id,
                    company_id=run.company_id,
                    run_reference=run.run_reference,
                    run_label=run.run_label,
                    period_year=run.period_year,
                    period_month=run.period_month,
                    status_code=run.status_code,
                    currency_code=run.currency_code,
                    run_date=run.run_date,
                    payment_date=run.payment_date,
                    employee_count=0,
                    total_net_payable=Decimal("0"),
                    posted_journal_entry_id=run.posted_journal_entry_id,
                    run_type_code=getattr(run, "run_type_code", "regular") or "regular",
                    run_sequence=getattr(run, "run_sequence", 1) or 1,
                )
                emp_dto = self._to_run_employee_list_dto(emp_row)
                result.append((run_dto, emp_dto))
            return result

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
                run_type_code="regular",
                run_sequence=repo.next_run_sequence(
                    company_id, cmd.period_year, cmd.period_month, "regular"
                ),
            )
            repo.save(run)
            uow.session.flush()
            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=None,
                to_state="draft",
                description=f"Created payroll run '{run.run_reference}'.",
                context={"period_year": run.period_year, "period_month": run.period_month},
            )
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
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="monthly_run",
                    step="run_created",
                    event_code="monthly_run.run_created",
                    context={
                        "company_id": company_id,
                        "period_year": cmd.period_year,
                        "period_month": cmd.period_month,
                    },
                )
            return self._to_run_dto(run)

    def create_offcycle_run(
        self, company_id: int, cmd: CreateOffCyclePayrollRunCommand
    ) -> PayrollRunDetailDTO:
        self._permission_service.require_permission(PAYROLL_RUN_CREATE)
        self._validate_period(cmd.period_year, cmd.period_month)
        employee_ids = tuple(dict.fromkeys(int(emp_id) for emp_id in cmd.employee_ids))
        if not employee_ids:
            raise ValidationError("Select at least one employee for an off-cycle payroll run.")
        reason_code = (cmd.off_cycle_reason_code or "").strip()
        if not reason_code:
            raise ValidationError("An off-cycle reason is required.")

        with self._uow_factory() as uow:
            repo = self._run_repo_factory(uow.session)
            employee_repo = self._employee_repo_factory(uow.session)
            missing_ids = [
                employee_id
                for employee_id in employee_ids
                if employee_repo.get_by_id(company_id, employee_id) is None
            ]
            if missing_ids:
                raise ValidationError(
                    "One or more selected employees do not exist for this company: "
                    + ", ".join(str(employee_id) for employee_id in missing_ids)
                )
            if cmd.source_run_id is not None and repo.get_by_id(company_id, cmd.source_run_id) is None:
                raise ValidationError("The selected source payroll run was not found.")

            ref = self._numbering_service.issue_next_number(
                uow.session, company_id, _RUN_DOC_TYPE
            )
            run = PayrollRun(
                company_id=company_id,
                run_reference=ref,
                run_label=cmd.run_label
                or f"{_CALENDAR_MONTHS[cmd.period_month]} {cmd.period_year} Off-cycle Payroll",
                period_year=cmd.period_year,
                period_month=cmd.period_month,
                status_code="draft",
                currency_code=cmd.currency_code,
                run_date=cmd.run_date,
                payment_date=cmd.payment_date,
                notes=cmd.notes,
                run_type_code="off_cycle",
                run_sequence=repo.next_run_sequence(
                    company_id, cmd.period_year, cmd.period_month, "off_cycle"
                ),
                off_cycle_reason_code=reason_code,
                off_cycle_employee_ids=json.dumps(list(employee_ids)),
                source_run_id=cmd.source_run_id,
            )
            repo.save(run)
            uow.session.flush()
            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=None,
                to_state="draft",
                description=f"Created off-cycle payroll run '{run.run_reference}'.",
                context={
                    "period_year": run.period_year,
                    "period_month": run.period_month,
                    "employee_count": len(employee_ids),
                    "off_cycle_reason_code": run.off_cycle_reason_code,
                },
            )
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_OFFCYCLE_RUN_CREATED",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=f"Created off-cycle payroll run '{run.run_reference}'.",
                    detail_json=json.dumps(
                        {
                            "run_reference": run.run_reference,
                            "period_year": run.period_year,
                            "period_month": run.period_month,
                            "employee_ids": list(employee_ids),
                            "off_cycle_reason_code": run.off_cycle_reason_code,
                            "source_run_id": run.source_run_id,
                        }
                    ),
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
            employee_scope = self._employee_scope_for_run(run)
            if employee_scope is not None:
                employees = [emp for emp in employees if emp.id in employee_scope]

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
            # Bulk pre-load profiles and assignments to avoid N+1 queries when
            # the run includes many employees. Single round-trip per repo.
            profile_map = profile_repo.map_active_for_period(company_id, period_date)
            assignment_map = assignment_repo.map_active_for_period(company_id, period_date)

            # Pre-load pending corrections for the period (optional — only when
            # correction_repository_factory is wired into this service).
            correction_map: dict[int, list[object]] = {}
            if self._correction_repo_factory is not None:
                corr_repo = self._correction_repo_factory(uow.session)
                raw_corrections = corr_repo.list_pending_for_period(
                    company_id,
                    run.period_year,
                    run.period_month,
                    employee_ids=tuple(emp.id for emp in employees) or None,
                )
                for corr in raw_corrections:
                    correction_map.setdefault(corr.employee_id, []).append(corr)

            included_count = 0
            error_count = 0

            for emp in employees:
                profile = profile_map.get(emp.id)
                if profile is None:
                    # No profile — record as error row
                    err_row = PayrollRunEmployee(
                        company_id=company_id,
                        run_id=run_id,
                        employee_id=emp.id,
                        status_code="error",
                        calculation_notes="No active compensation for this period.",
                    )
                    run_emp_repo.save(err_row)
                    error_count += 1
                    continue

                assignments = assignment_map.get(emp.id, [])

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

                # Apply any pending corrections for this employee.
                emp_corrections = correction_map.get(emp.id, [])
                if emp_corrections:
                    self._apply_pending_corrections(calc_result, emp_corrections)

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

                # Mark pending corrections applied and emit audit events.
                if emp_corrections:
                    _applied_at = datetime.now(timezone.utc)
                    self._mark_corrections_applied(
                        emp_corrections,
                        run_id=run_id,
                        run_employee_id=run_emp.id,
                        applied_at=_applied_at,
                    )
                    for _corr in emp_corrections:
                        self._audit_service.record_event_in_session(
                            uow.session,
                            company_id,
                            RecordAuditEventCommand(
                                event_type_code="PAYROLL_CORRECTION_APPLIED",
                                module_code="payroll",
                                entity_type="employee_payroll_correction",
                                entity_id=_corr.id,
                                description=(
                                    f"Applied correction {_corr.id} to run employee {run_emp.id}."
                                ),
                                detail_json=json.dumps({
                                    "correction_id": _corr.id,
                                    "run_id": run_id,
                                    "run_employee_id": run_emp.id,
                                    "employee_id": emp.id,
                                    "amount": str(_corr.correction_amount),
                                }),
                            ),
                        )

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
                self._persist_calc_steps(
                    uow.session,
                    company_id=company_id,
                    run_id=run_id,
                    run_employee_id=run_emp.id,
                    employee_id=emp.id,
                    calc_result=calc_result,
                )

            previous_status = run.status_code
            run.status_code = "calculated"
            run.calculated_at = datetime.now(timezone.utc)
            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=previous_status,
                to_state="calculated",
                description=f"Calculated payroll run '{run.run_reference}'.",
                context={
                    "included_employee_count": included_count,
                    "error_employee_count": error_count,
                },
            )
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
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="monthly_run",
                    step="run_calculated",
                    event_code="monthly_run.run_calculated",
                    context={
                        "company_id": company_id,
                        "period_year": run.period_year,
                        "period_month": run.period_month,
                        "included_count": included_count,
                    },
                )
            return self._to_run_dto(run)

    def set_run_employee_inclusion(
        self,
        company_id: int,
        run_employee_id: int,
        *,
        is_included: bool,
        exclusion_reason: str | None = None,
    ) -> PayrollRunEmployeeListItemDTO:
        """Toggle a single run-employee row between included and excluded.

        Allowed only while the parent run is still in ``calculated`` status
        (i.e. after calculate, before approve). Once approved or posted, the
        set of employees in the run is frozen for accounting integrity.

        Errored rows (``status_code == 'error'``) cannot be toggled here —
        they must be resolved through recalculation.
        """
        self._permission_service.require_permission(PAYROLL_RUN_CALCULATE)
        with self._uow_factory() as uow:
            emp_repo = self._run_employee_repo_factory(uow.session)
            row = emp_repo.get_by_id(company_id, run_employee_id)
            if row is None:
                raise NotFoundError("Employee payroll row not found.")

            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, row.run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            if run.status_code != "calculated":
                raise ValidationError(
                    "Employees can only be included or excluded on a calculated run. "
                    "Approved or posted runs are frozen."
                )
            if row.status_code == "error":
                raise ValidationError(
                    "This row has a calculation error and cannot be toggled. "
                    "Recalculate the run to clear the error first."
                )

            new_status = "included" if is_included else "excluded"
            if is_included:
                reason: str | None = None
            else:
                reason = (exclusion_reason or "").strip() or None
                if reason is None:
                    raise ValidationError(
                        "A reason is required when excluding an employee from a run."
                    )

            if row.status_code == new_status and (row.exclusion_reason or None) == reason:
                # Idempotent no-op
                uow.session.refresh(row)
                return self._to_run_employee_list_dto(row)

            row.status_code = new_status
            row.exclusion_reason = reason
            emp = row.employee
            emp_label = emp.display_name if emp else f"#{row.employee_id}"
            verb = "Included" if is_included else "Excluded"
            description = (
                f"{verb} {emp_label} from payroll run '{run.run_reference}'."
                + (f" Reason: {reason}." if reason else "")
            )
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_EMPLOYEE_INCLUSION_CHANGED",
                    module_code="payroll",
                    entity_type="payroll_run_employee",
                    entity_id=row.id,
                    description=description,
                ),
            )
            uow.commit()
            uow.session.refresh(row)
            return self._to_run_employee_list_dto(row)

    def submit_run_for_review(
        self,
        company_id: int,
        run_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> None:
        self._permission_service.require_permission(PAYROLL_RUN_SUBMIT)
        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            if run.status_code != "calculated":
                raise ValidationError("Only calculated payroll runs can be submitted for review.")

            previous_status = run.status_code
            run.status_code = "submitted_for_review"
            run.submitted_at = datetime.now(timezone.utc)
            run.submitted_by_user_id = self._resolve_actor_user_id(actor_user_id)
            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=previous_status,
                to_state="submitted_for_review",
                description=f"Submitted payroll run '{run.run_reference}' for review.",
            )
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_SUBMITTED_FOR_REVIEW",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=f"Submitted payroll run '{run.run_reference}' for review.",
                ),
            )
            uow.commit()
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="monthly_run",
                    step="run_submitted",
                    event_code="monthly_run.run_submitted",
                    context={
                        "company_id": company_id,
                        "period_year": run.period_year,
                        "period_month": run.period_month,
                    },
                )

    def send_back_run(
        self,
        company_id: int,
        run_id: int,
        reason: str,
        *,
        actor_user_id: int | None = None,
    ) -> None:
        self._permission_service.require_permission(PAYROLL_RUN_SEND_BACK)
        cleaned_reason = reason.strip()
        if not cleaned_reason:
            raise ValidationError("A reason is required when sending back a payroll run.")

        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            if run.status_code != "submitted_for_review":
                raise ValidationError("Only submitted payroll runs can be sent back.")

            previous_status = run.status_code
            run.status_code = "calculated"
            run.sent_back_at = datetime.now(timezone.utc)
            run.sent_back_by_user_id = self._resolve_actor_user_id(actor_user_id)
            run.sent_back_reason = cleaned_reason
            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=previous_status,
                to_state="calculated",
                description=f"Sent back payroll run '{run.run_reference}' for correction.",
                reason=cleaned_reason,
            )
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_RUN_SENT_BACK",
                    module_code="payroll",
                    entity_type="payroll_run",
                    entity_id=run.id,
                    description=f"Sent back payroll run '{run.run_reference}' for correction.",
                    detail_json=json.dumps({"reason": cleaned_reason}),
                ),
            )
            uow.commit()
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="monthly_run",
                    step="run_sent_back",
                    event_code="monthly_run.run_sent_back",
                    context={
                        "company_id": company_id,
                        "period_year": run.period_year,
                        "period_month": run.period_month,
                    },
                )

    def approve_run(
        self,
        company_id: int,
        run_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> None:
        self._permission_service.require_permission(PAYROLL_RUN_APPROVE)
        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")
            sod_strict = self._is_sod_strict(uow.session, company_id)
            if run.status_code == "calculated":
                if sod_strict:
                    raise ValidationError(
                        "Segregation of duties requires submission before approval."
                    )
            elif run.status_code != "submitted_for_review":
                raise ValidationError("Only submitted or calculated payroll runs can be approved.")

            actor_id = self._resolve_actor_user_id(actor_user_id)
            if sod_strict and actor_id is not None and run.submitted_by_user_id == actor_id:
                raise ValidationError(
                    "Segregation of duties prevents approving your own submitted payroll run."
                )
            previous_status = run.status_code
            run.status_code = "approved"
            run.approved_at = datetime.now(timezone.utc)
            run.approved_by_user_id = actor_id
            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=previous_status,
                to_state="approved",
                description=f"Approved payroll run '{run.run_reference}'.",
            )
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
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="monthly_run",
                    step="run_approved",
                    event_code="monthly_run.run_approved",
                    context={
                        "company_id": company_id,
                        "period_year": run.period_year,
                        "period_month": run.period_month,
                    },
                )

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
            if run.status_code == "submitted_for_review":
                raise ValidationError(
                    "Submitted payroll runs must be sent back before they can be voided."
                )
            if run.status_code == "approved":
                raise ValidationError(
                    "Approved runs cannot be voided. Contact your administrator."
                )
            previous_status = run.status_code
            run.status_code = "voided"
            self._record_state_transition_in_session(
                uow.session,
                company_id,
                run,
                from_state=previous_status,
                to_state="voided",
                description=f"Voided payroll run '{run.run_reference}'.",
            )
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
            if self._telemetry is not None:
                self._telemetry.record_funnel_step(
                    funnel="monthly_run",
                    step="run_voided",
                    event_code="monthly_run.run_voided",
                    context={
                        "company_id": company_id,
                        "period_year": run.period_year,
                        "period_month": run.period_month,
                    },
                )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_actor_user_id(self, actor_user_id: int | None = None) -> int | None:
        if actor_user_id is not None:
            return actor_user_id
        return getattr(self._app_context, "current_user_id", None)

    def _is_sod_strict(self, session: Session, company_id: int) -> bool:
        if self._setting_repo_factory is None:
            return False
        setting = self._setting_repo_factory(session).get_by_company(company_id)
        return bool(getattr(setting, "sod_strict", False))

    def _record_state_transition_in_session(
        self,
        session: Session,
        company_id: int,
        run: PayrollRun,
        *,
        from_state: str | None,
        to_state: str,
        description: str,
        reason: str | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        recorder = getattr(self._audit_service, "record_state_transition_in_session", None)
        if recorder is None:
            return
        recorder(
            session,
            company_id,
            module_code="payroll",
            entity_type="payroll_run",
            entity_id=run.id,
            from_state=from_state,
            to_state=to_state,
            description=description,
            reason=reason,
            context={"run_reference": run.run_reference, **(context or {})},
        )

    @staticmethod
    def _employee_scope_for_run(run: object) -> set[int] | None:
        if getattr(run, "run_type_code", None) != "off_cycle":
            return None
        raw_ids = getattr(run, "off_cycle_employee_ids", None)
        if not raw_ids:
            return set()
        try:
            parsed = json.loads(raw_ids)
        except (TypeError, ValueError):
            return set()
        if not isinstance(parsed, list):
            return set()
        return {int(value) for value in parsed if value is not None}

    @staticmethod
    def _apply_pending_corrections(
        calc_result: EmployeeCalculationResult,
        corrections: Iterable[object],
    ) -> None:
        for correction in corrections:
            if getattr(correction, "employee_id", None) != calc_result.employee_id:
                continue
            component = correction.component
            amount = Decimal(str(correction.correction_amount))
            component_type = component.component_type_code
            calc_result.lines.append(
                EngineLineResult(
                    component_id=component.id,
                    component_type_code=component_type,
                    calculation_basis=amount,
                    rate_applied=None,
                    component_amount=amount,
                )
            )
            if component_type == "earning":
                calc_result.gross_earnings += amount
                calc_result.total_earnings += amount
                calc_result.net_payable += amount
                calc_result.employer_cost_base += amount
            elif component_type in {"deduction", "tax"}:
                if component_type == "tax":
                    calc_result.total_taxes += amount
                else:
                    calc_result.total_employee_deductions += amount
                calc_result.net_payable -= amount
            elif component_type == "employer_contribution":
                calc_result.total_employer_contributions += amount
                calc_result.employer_cost_base += amount

    @staticmethod
    def _mark_corrections_applied(
        corrections: Iterable[object],
        *,
        run_id: int,
        run_employee_id: int,
        applied_at: object,
    ) -> None:
        for correction in corrections:
            correction.status_code = "applied"
            correction.applied_run_id = run_id
            correction.applied_run_employee_id = run_employee_id
            correction.applied_at = applied_at

    def _persist_calc_steps(
        self,
        session: Session,
        *,
        company_id: int,
        run_id: int,
        run_employee_id: int,
        employee_id: int,
        calc_result: EmployeeCalculationResult,
    ) -> None:
        if self._trace_repo_factory is None or not calc_result.calc_steps:
            return
        traces = [
            PayrollCalculationTrace(
                company_id=company_id,
                run_id=run_id,
                run_employee_id=run_employee_id,
                employee_id=employee_id,
                sequence_number=step.sequence_number,
                stage_code=step.stage_code,
                component_id=step.component_id,
                formula_code=step.formula_code,
                input_json=step.input_json,
                output_json=step.output_json,
                amount=step.amount,
            )
            for step in calc_result.calc_steps
        ]
        self._trace_repo_factory(session).save_many(traces)

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
            approved_by_user_id=r.approved_by_user_id,
            submitted_at=r.submitted_at,
            submitted_by_user_id=r.submitted_by_user_id,
            sent_back_at=r.sent_back_at,
            sent_back_by_user_id=r.sent_back_by_user_id,
            sent_back_reason=r.sent_back_reason,
            posted_at=r.posted_at,
            posted_by_user_id=r.posted_by_user_id,
            posted_journal_entry_id=r.posted_journal_entry_id,
            run_type_code=r.run_type_code,
            run_sequence=r.run_sequence,
            off_cycle_reason_code=r.off_cycle_reason_code,
            off_cycle_employee_ids=tuple(sorted(PayrollRunService._employee_scope_for_run(r) or ())),
            source_run_id=r.source_run_id,
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
            exclusion_reason=r.exclusion_reason,
            payment_status_code=getattr(r, "payment_status_code", "unpaid") or "unpaid",
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
            exclusion_reason=r.exclusion_reason,
            lines=lines,
        )
