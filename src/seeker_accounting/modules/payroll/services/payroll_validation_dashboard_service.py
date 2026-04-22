"""Payroll Validation Dashboard Service — comprehensive readiness assessment.

Runs readiness and consistency checks across payroll setup, effective-dated data,
mapping integrity, rule configuration, and detectable settlement anomalies.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.fiscal_periods.repositories.fiscal_period_repository import (
    FiscalPeriodRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_role_mapping_repository import (
    AccountRoleMappingRepository,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.payroll.dto.payroll_validation_dashboard_dto import (
    ValidationCheckDTO,
    ValidationDashboardResultDTO,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_SETUP_MANAGE
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
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_input_batch_repository import (
    PayrollInputBatchRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_payment_record_repository import (
    PayrollPaymentRecordRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_remittance_repository import (
    PayrollRemittanceBatchRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import (
    PayrollRuleSetRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunEmployeeRepository,
    PayrollRunRepository,
)
from seeker_accounting.modules.payroll.statutory_packs import pack_registry

CompanyPayrollSettingRepositoryFactory = Callable[[Session], CompanyPayrollSettingRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
CompensationProfileRepositoryFactory = Callable[[Session], CompensationProfileRepository]
ComponentAssignmentRepositoryFactory = Callable[[Session], ComponentAssignmentRepository]
PayrollComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]
PayrollRuleSetRepositoryFactory = Callable[[Session], PayrollRuleSetRepository]
FiscalPeriodRepositoryFactory = Callable[[Session], FiscalPeriodRepository]
AccountRoleMappingRepositoryFactory = Callable[[Session], AccountRoleMappingRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
PayrollInputBatchRepositoryFactory = Callable[[Session], PayrollInputBatchRepository]
PayrollPaymentRecordRepositoryFactory = Callable[[Session], PayrollPaymentRecordRepository]
PayrollRemittanceBatchRepositoryFactory = Callable[[Session], PayrollRemittanceBatchRepository]
PayrollRunRepositoryFactory = Callable[[Session], PayrollRunRepository]
PayrollRunEmployeeRepositoryFactory = Callable[[Session], PayrollRunEmployeeRepository]

_TOLERANCE = Decimal("0.005")
_BIK_CODES = frozenset({"HOUSING_BIK", "TRANSPORT_BIK", "VEHICLE_BIK", "MEAL_BIK"})


class PayrollValidationDashboardService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        settings_repo_factory: CompanyPayrollSettingRepositoryFactory,
        employee_repo_factory: EmployeeRepositoryFactory,
        profile_repo_factory: CompensationProfileRepositoryFactory,
        assignment_repo_factory: ComponentAssignmentRepositoryFactory,
        component_repo_factory: PayrollComponentRepositoryFactory,
        rule_set_repo_factory: PayrollRuleSetRepositoryFactory,
        fiscal_period_repo_factory: FiscalPeriodRepositoryFactory,
        role_mapping_repo_factory: AccountRoleMappingRepositoryFactory,
        account_repo_factory: AccountRepositoryFactory,
        input_batch_repo_factory: PayrollInputBatchRepositoryFactory,
        payment_record_repo_factory: PayrollPaymentRecordRepositoryFactory,
        remittance_batch_repo_factory: PayrollRemittanceBatchRepositoryFactory,
        run_repo_factory: PayrollRunRepositoryFactory,
        run_employee_repo_factory: PayrollRunEmployeeRepositoryFactory,
        permission_service: PermissionService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._settings_repo_factory = settings_repo_factory
        self._employee_repo_factory = employee_repo_factory
        self._profile_repo_factory = profile_repo_factory
        self._assignment_repo_factory = assignment_repo_factory
        self._component_repo_factory = component_repo_factory
        self._rule_set_repo_factory = rule_set_repo_factory
        self._period_repo_factory = fiscal_period_repo_factory
        self._role_mapping_repo_factory = role_mapping_repo_factory
        self._account_repo_factory = account_repo_factory
        self._input_batch_repo_factory = input_batch_repo_factory
        self._payment_record_repo_factory = payment_record_repo_factory
        self._remittance_batch_repo_factory = remittance_batch_repo_factory
        self._run_repo_factory = run_repo_factory
        self._run_employee_repo_factory = run_employee_repo_factory
        self._permission_service = permission_service

    def run_full_assessment(
        self,
        company_id: int,
        period_year: int,
        period_month: int,
    ) -> ValidationDashboardResultDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        period_date = date(period_year, period_month, 1)
        checks: list[ValidationCheckDTO] = []

        with self._uow_factory() as uow:
            settings_repo = self._settings_repo_factory(uow.session)
            emp_repo = self._employee_repo_factory(uow.session)
            profile_repo = self._profile_repo_factory(uow.session)
            assignment_repo = self._assignment_repo_factory(uow.session)
            comp_repo = self._component_repo_factory(uow.session)
            rule_repo = self._rule_set_repo_factory(uow.session)
            period_repo = self._period_repo_factory(uow.session)
            role_repo = self._role_mapping_repo_factory(uow.session)
            account_repo = self._account_repo_factory(uow.session)
            input_batch_repo = self._input_batch_repo_factory(uow.session)
            payment_repo = self._payment_record_repo_factory(uow.session)
            remittance_repo = self._remittance_batch_repo_factory(uow.session)
            run_repo = self._run_repo_factory(uow.session)
            run_employee_repo = self._run_employee_repo_factory(uow.session)

            settings = settings_repo.get_by_company(company_id)
            employees = emp_repo.list_by_company(company_id, active_only=True)
            profiles = profile_repo.list_by_company(company_id, active_only=True)
            assignments = assignment_repo.list_by_company(company_id, active_only=True)
            components = comp_repo.list_by_company(company_id, active_only=True)
            rule_sets = rule_repo.list_by_company(company_id, active_only=True)
            input_batches = input_batch_repo.get_approved_for_period(company_id, period_year, period_month)

            self._append_setup_checks(checks, settings)
            self._append_pack_verification_checks(checks, settings)
            self._append_period_checks(checks, period_repo, company_id, period_date, period_year, period_month)
            self._append_payable_mapping_checks(checks, role_repo, account_repo, company_id)

            if not employees:
                checks.append(
                    ValidationCheckDTO(
                        check_code="NO_ACTIVE_EMPLOYEES",
                        category="employees",
                        severity="error",
                        title="No Active Employees",
                        message="There are no active employees. Add employees in Payroll Setup.",
                    )
                )

            ready_count = self._append_employee_checks(
                checks,
                employees,
                profiles,
                assignments,
                company_id,
                period_date,
                period_year,
                period_month,
            )
            self._append_component_checks(checks, components)
            rule_sets_by_code = self._append_rule_checks(
                checks,
                components,
                rule_sets,
                company_id,
                period_date,
                rule_repo,
                input_batches,
                settings,
            )
            self._append_fallback_reliance_check(
                checks,
                components,
                rule_sets_by_code,
                input_batches,
            )
            self._append_payment_consistency_checks(
                checks,
                company_id,
                run_repo,
                run_employee_repo,
                payment_repo,
            )
            self._append_remittance_consistency_checks(checks, company_id, remittance_repo)

        return ValidationDashboardResultDTO(
            company_id=company_id,
            period_year=period_year,
            period_month=period_month,
            checks=tuple(checks),
            employee_count=len(employees),
            ready_employee_count=ready_count,
        )

    def _append_setup_checks(self, checks: list[ValidationCheckDTO], settings) -> None:
        if settings is None:
            checks.append(
                ValidationCheckDTO(
                    check_code="NO_PAYROLL_SETTINGS",
                    category="setup",
                    severity="error",
                    title="Payroll Settings Missing",
                    message="Company payroll settings have not been configured. Go to Payroll Setup.",
                )
            )
            return
        if not settings.statutory_pack_version_code:
            checks.append(
                ValidationCheckDTO(
                    check_code="NO_STATUTORY_PACK",
                    category="setup",
                    severity="warning",
                    title="No Statutory Pack Applied",
                    message="No statutory pack has been applied. Apply a pack in Payroll Operations > Statutory Packs.",
                )
            )

    def _append_pack_verification_checks(
        self,
        checks: list[ValidationCheckDTO],
        settings,
    ) -> None:
        """Surface statutory pack verification quality: provisional / unverified items."""
        if settings is None or not settings.statutory_pack_version_code:
            return

        descriptor = pack_registry.get_pack_by_code(settings.statutory_pack_version_code)
        if descriptor is None:
            return

        pack_mod = descriptor.pack_module
        get_summary = getattr(pack_mod, "get_pack_verification_summary", None)
        if get_summary is None:
            return

        summary = get_summary()
        provisional = summary.get("provisional", 0)
        unverified = summary.get("unverified", 0)

        if unverified > 0:
            checks.append(
                ValidationCheckDTO(
                    check_code="PACK_UNVERIFIED_ITEMS",
                    category="setup",
                    severity="error",
                    title="Statutory Pack Contains Unverified Items",
                    message=(
                        f"Pack '{descriptor.pack_code}' has {unverified} unverified item(s). "
                        "These items use placeholder values and must be confirmed against official "
                        "statutory sources before production payroll runs."
                    ),
                )
            )

        if provisional > 0:
            checks.append(
                ValidationCheckDTO(
                    check_code="PACK_PROVISIONAL_ITEMS",
                    category="setup",
                    severity="info",
                    title="Statutory Pack Has Provisional Items",
                    message=(
                        f"Pack '{descriptor.pack_code}' has {provisional} provisional item(s) "
                        "(e.g. CRTV brackets, TDL amounts). These are consistent with known "
                        "regulations but exact values should be confirmed against the current "
                        "Finance Law / DGI circulars."
                    ),
                )
            )

    def _append_period_checks(
        self,
        checks: list[ValidationCheckDTO],
        period_repo: FiscalPeriodRepository,
        company_id: int,
        period_date: date,
        period_year: int,
        period_month: int,
    ) -> None:
        period = period_repo.get_covering_date(company_id, period_date)
        if period is None:
            checks.append(
                ValidationCheckDTO(
                    check_code="NO_FISCAL_PERIOD",
                    category="period",
                    severity="error",
                    title="No Fiscal Period",
                    message=f"No fiscal period covers {period_year}-{period_month:02d}. Create one in Fiscal Periods.",
                )
            )
            return
        if period.status_code == "LOCKED":
            checks.append(
                ValidationCheckDTO(
                    check_code="PERIOD_LOCKED",
                    category="period",
                    severity="error",
                    title="Fiscal Period Locked",
                    message=f"Period '{period.period_code}' is locked. Unlock it before posting payroll.",
                )
            )
        elif period.status_code != "OPEN":
            checks.append(
                ValidationCheckDTO(
                    check_code="PERIOD_NOT_OPEN",
                    category="period",
                    severity="warning",
                    title="Fiscal Period Not Open",
                    message=f"Period '{period.period_code}' has status '{period.status_code}'. It must be OPEN for posting.",
                )
            )

    def _append_payable_mapping_checks(
        self,
        checks: list[ValidationCheckDTO],
        role_repo: AccountRoleMappingRepository,
        account_repo: AccountRepository,
        company_id: int,
    ) -> None:
        payable_mapping = role_repo.get_by_role_code(company_id, "payroll_payable")
        if payable_mapping is None:
            checks.append(
                ValidationCheckDTO(
                    check_code="NO_PAYROLL_PAYABLE_ACCOUNT",
                    category="accounts",
                    severity="error",
                    title="Payroll Payable Account Not Mapped",
                    message="The 'payroll_payable' account role is not mapped. Configure it in Accounting Setup > Account Roles.",
                )
            )
            return

        account = account_repo.get_by_id(company_id, payable_mapping.account_id)
        if account is None:
            checks.append(
                ValidationCheckDTO(
                    check_code="INVALID_PAYROLL_PAYABLE_ACCOUNT",
                    category="accounts",
                    severity="error",
                    title="Payroll Payable Account Invalid",
                    message="The mapped payroll payable account no longer exists.",
                )
            )
            return
        if not account.is_active:
            checks.append(
                ValidationCheckDTO(
                    check_code="INACTIVE_PAYROLL_PAYABLE_ACCOUNT",
                    category="accounts",
                    severity="error",
                    title="Payroll Payable Account Inactive",
                    message=f"Payroll payable account '{account.account_code}' is inactive.",
                )
            )
        if not account.allow_manual_posting:
            checks.append(
                ValidationCheckDTO(
                    check_code="NON_POSTABLE_PAYROLL_PAYABLE_ACCOUNT",
                    category="accounts",
                    severity="error",
                    title="Payroll Payable Account Non-Postable",
                    message=f"Payroll payable account '{account.account_code}' does not allow posting.",
                )
            )

    def _append_employee_checks(
        self,
        checks: list[ValidationCheckDTO],
        employees: list,
        profiles: list,
        assignments: list,
        company_id: int,
        period_date: date,
        period_year: int,
        period_month: int,
    ) -> int:
        profiles_by_employee: dict[int, list] = defaultdict(list)
        for profile in profiles:
            profiles_by_employee[profile.employee_id].append(profile)

        assignments_by_employee: dict[int, list] = defaultdict(list)
        assignments_by_key: dict[tuple[int, int], list] = defaultdict(list)
        for assignment in assignments:
            assignments_by_employee[assignment.employee_id].append(assignment)
            assignments_by_key[(assignment.employee_id, assignment.component_id)].append(assignment)

        self._append_profile_overlap_checks(checks, profiles_by_employee)
        self._append_assignment_overlap_checks(checks, assignments_by_key)

        ready_count = 0
        for employee in employees:
            employee_has_error = False
            employee_profiles = profiles_by_employee.get(employee.id, [])
            active_profiles = [p for p in employee_profiles if self._covers_period(p, period_date)]
            if not employee_profiles:
                checks.append(
                    ValidationCheckDTO(
                        check_code="NO_COMPENSATION_PROFILE",
                        category="employees",
                        severity="error",
                        title="Missing Compensation Profile",
                        message=f"{employee.display_name} has no compensation profile configured.",
                        entity_type="employee",
                        entity_id=employee.id,
                        entity_label=employee.display_name,
                    )
                )
                employee_has_error = True
            elif not active_profiles:
                checks.append(
                    ValidationCheckDTO(
                        check_code="EFFECTIVE_DATE_GAP",
                        category="employees",
                        severity="error",
                        title="Compensation Profile Gap",
                        message=(
                            f"{employee.display_name} has compensation profiles, but none cover "
                            f"{period_year}-{period_month:02d}."
                        ),
                        entity_type="employee",
                        entity_id=employee.id,
                        entity_label=employee.display_name,
                    )
                )
                employee_has_error = True
            elif len(active_profiles) > 1:
                checks.append(
                    ValidationCheckDTO(
                        check_code="EFFECTIVE_DATE_AMBIGUITY",
                        category="employees",
                        severity="error",
                        title="Compensation Profile Ambiguity",
                        message=(
                            f"{employee.display_name} has multiple active compensation profiles for "
                            f"{period_year}-{period_month:02d}."
                        ),
                        entity_type="employee",
                        entity_id=employee.id,
                        entity_label=employee.display_name,
                    )
                )
                employee_has_error = True

            employee_assignments = assignments_by_employee.get(employee.id, [])
            active_assignments = [a for a in employee_assignments if self._covers_period(a, period_date)]
            if not active_assignments:
                checks.append(
                    ValidationCheckDTO(
                        check_code="NO_COMPONENT_ASSIGNMENTS",
                        category="employees",
                        severity="warning",
                        title="No Component Assignments",
                        message=(
                            f"{employee.display_name} has no active component assignments for "
                            f"{period_year}-{period_month:02d}."
                        ),
                        entity_type="employee",
                        entity_id=employee.id,
                        entity_label=employee.display_name,
                    )
                )

            ambiguous_components = {
                assignment.component_id
                for assignment in active_assignments
                if len(
                    [
                        other
                        for other in active_assignments
                        if other.component_id == assignment.component_id
                    ]
                ) > 1
            }
            if ambiguous_components:
                checks.append(
                    ValidationCheckDTO(
                        check_code="ASSIGNMENT_EFFECTIVE_DATE_AMBIGUITY",
                        category="employees",
                        severity="error",
                        title="Recurring Assignment Ambiguity",
                        message=(
                            f"{employee.display_name} has multiple active assignments for one or more components "
                            f"in {period_year}-{period_month:02d}."
                        ),
                        entity_type="employee",
                        entity_id=employee.id,
                        entity_label=employee.display_name,
                    )
                )
                employee_has_error = True

            if employee.termination_date and employee.termination_date < period_date:
                checks.append(
                    ValidationCheckDTO(
                        check_code="TERMINATED_STILL_ACTIVE",
                        category="employees",
                        severity="warning",
                        title="Terminated Employee Still Active",
                        message=(
                            f"{employee.display_name} was terminated on {employee.termination_date} but is still marked active."
                        ),
                        entity_type="employee",
                        entity_id=employee.id,
                        entity_label=employee.display_name,
                    )
                )

            if not employee_has_error:
                ready_count += 1

        return ready_count

    def _append_profile_overlap_checks(
        self,
        checks: list[ValidationCheckDTO],
        profiles_by_employee: dict[int, list],
    ) -> None:
        for employee_id, profiles in profiles_by_employee.items():
            ordered = sorted(profiles, key=lambda item: item.effective_from)
            for index, current in enumerate(ordered):
                for candidate in ordered[index + 1 :]:
                    if self._ranges_overlap(
                        current.effective_from,
                        current.effective_to,
                        candidate.effective_from,
                        candidate.effective_to,
                    ):
                        checks.append(
                            ValidationCheckDTO(
                                check_code="OVERLAPPING_COMPENSATION_PROFILES",
                                category="employees",
                                severity="error",
                                title="Overlapping Compensation Profiles",
                                message=(
                                    f"Employee {current.employee.display_name if current.employee else employee_id} "
                                    "has overlapping active compensation profiles."
                                ),
                                entity_type="employee",
                                entity_id=employee_id,
                                entity_label=current.employee.display_name if current.employee else None,
                            )
                        )
                        break
                else:
                    continue
                break

    def _append_assignment_overlap_checks(
        self,
        checks: list[ValidationCheckDTO],
        assignments_by_key: dict[tuple[int, int], list],
    ) -> None:
        for (employee_id, component_id), assignments in assignments_by_key.items():
            ordered = sorted(assignments, key=lambda item: item.effective_from)
            for index, current in enumerate(ordered):
                for candidate in ordered[index + 1 :]:
                    if self._ranges_overlap(
                        current.effective_from,
                        current.effective_to,
                        candidate.effective_from,
                        candidate.effective_to,
                    ):
                        label = current.employee.display_name if current.employee else None
                        component_code = current.component.component_code if current.component else str(component_id)
                        checks.append(
                            ValidationCheckDTO(
                                check_code="OVERLAPPING_COMPONENT_ASSIGNMENTS",
                                category="employees",
                                severity="error",
                                title="Overlapping Recurring Component Assignments",
                                message=(
                                    f"{label or f'Employee {employee_id}'} has overlapping recurring assignments "
                                    f"for component '{component_code}'."
                                ),
                                entity_type="employee",
                                entity_id=employee_id,
                                entity_label=label,
                            )
                        )
                        break
                else:
                    continue
                break

    def _append_component_checks(self, checks: list[ValidationCheckDTO], components: list) -> None:
        expense_types = {"earning", "employer_contribution"}
        liability_types = {"deduction", "tax", "employer_contribution"}

        for component in components:
            if component.component_type_code in expense_types and component.expense_account_id is None:
                checks.append(
                    ValidationCheckDTO(
                        check_code="MISSING_EXPENSE_ACCOUNT",
                        category="accounts",
                        severity="error",
                        title="Missing Expense Account",
                        message=(
                            f"Component '{component.component_code}' ({component.component_name}) has no expense account mapped."
                        ),
                        entity_type="payroll_component",
                        entity_id=component.id,
                        entity_label=component.component_code,
                    )
                )
            if component.component_type_code in liability_types and component.liability_account_id is None:
                checks.append(
                    ValidationCheckDTO(
                        check_code="MISSING_LIABILITY_ACCOUNT",
                        category="accounts",
                        severity="error",
                        title="Missing Liability Account",
                        message=(
                            f"Component '{component.component_code}' ({component.component_name}) has no liability account mapped."
                        ),
                        entity_type="payroll_component",
                        entity_id=component.id,
                        entity_label=component.component_code,
                    )
                )

            if component.expense_account and not component.expense_account.is_active:
                checks.append(
                    ValidationCheckDTO(
                        check_code="INACTIVE_MAPPED_ACCOUNT",
                        category="accounts",
                        severity="error",
                        title="Inactive Mapped Expense Account",
                        message=(
                            f"Expense account '{component.expense_account.account_code}' mapped to component "
                            f"'{component.component_code}' is inactive."
                        ),
                        entity_type="payroll_component",
                        entity_id=component.id,
                        entity_label=component.component_code,
                    )
                )
            if component.expense_account and not component.expense_account.allow_manual_posting:
                checks.append(
                    ValidationCheckDTO(
                        check_code="NON_POSTABLE_MAPPED_ACCOUNT",
                        category="accounts",
                        severity="error",
                        title="Non-Postable Expense Account",
                        message=(
                            f"Expense account '{component.expense_account.account_code}' mapped to component "
                            f"'{component.component_code}' does not allow posting."
                        ),
                        entity_type="payroll_component",
                        entity_id=component.id,
                        entity_label=component.component_code,
                    )
                )
            if component.liability_account and not component.liability_account.is_active:
                checks.append(
                    ValidationCheckDTO(
                        check_code="INACTIVE_MAPPED_ACCOUNT",
                        category="accounts",
                        severity="error",
                        title="Inactive Mapped Liability Account",
                        message=(
                            f"Liability account '{component.liability_account.account_code}' mapped to component "
                            f"'{component.component_code}' is inactive."
                        ),
                        entity_type="payroll_component",
                        entity_id=component.id,
                        entity_label=component.component_code,
                    )
                )
            if component.liability_account and not component.liability_account.allow_manual_posting:
                checks.append(
                    ValidationCheckDTO(
                        check_code="NON_POSTABLE_MAPPED_ACCOUNT",
                        category="accounts",
                        severity="error",
                        title="Non-Postable Liability Account",
                        message=(
                            f"Liability account '{component.liability_account.account_code}' mapped to component "
                            f"'{component.component_code}' does not allow posting."
                        ),
                        entity_type="payroll_component",
                        entity_id=component.id,
                        entity_label=component.component_code,
                    )
                )

            if component.component_code in _BIK_CODES:
                if component.component_type_code != "earning":
                    checks.append(
                        ValidationCheckDTO(
                            check_code="BENEFITS_IN_KIND_SETUP_ISSUE",
                            category="setup",
                            severity="error",
                            title="Benefits-in-Kind Type Mismatch",
                            message=(
                                f"Benefits-in-kind component '{component.component_code}' must be configured as an earning."
                            ),
                            entity_type="payroll_component",
                            entity_id=component.id,
                            entity_label=component.component_code,
                        )
                    )
                if not component.is_taxable:
                    checks.append(
                        ValidationCheckDTO(
                            check_code="BENEFITS_IN_KIND_SETUP_ISSUE",
                            category="setup",
                            severity="warning",
                            title="Benefits-in-Kind Taxability Missing",
                            message=(
                                f"Benefits-in-kind component '{component.component_code}' is not marked taxable."
                            ),
                            entity_type="payroll_component",
                            entity_id=component.id,
                            entity_label=component.component_code,
                        )
                    )

    def _append_rule_checks(
        self,
        checks: list[ValidationCheckDTO],
        components: list,
        rule_sets: list,
        company_id: int,
        period_date: date,
        rule_repo: PayrollRuleSetRepository,
        input_batches: list,
        settings,
    ) -> dict[str, object | None]:
        expected_rules = {
            "EMPLOYEE_CNPS": "CNPS_EMPLOYEE_MAIN",
            "EMPLOYER_CNPS": "CNPS_EMPLOYER_MAIN",
            "IRPP": "DGI_IRPP_MAIN",
            "TDL": "TDL_MAIN",
            "ACCIDENT_RISK_EMPLOYER": "ACCIDENT_RISK_STANDARD",
            "CFC_HLF": "CCF_MAIN",
            "FNE_EMPLOYEE": "FNE_EMPLOYEE_MAIN",
            "FNE": "FNE_EMPLOYER_MAIN",
            "EMPLOYER_AF": "AF_MAIN",
            "CRTV": "CRTV_MAIN",
        }
        # Additional rule sets checked independently (not tied to a single component)
        statutory_rule_codes = {"DGI_IRPP_ABATTEMENT"}
        components_by_code = {component.component_code: component for component in components}
        rule_sets_by_code: dict[str, object | None] = {}

        all_rule_codes = set(expected_rules.values()) | {"OVERTIME_STANDARD"} | statutory_rule_codes
        for rule_code in all_rule_codes:
            rule_sets_by_code[rule_code] = rule_repo.get_by_code_and_date(company_id, rule_code, period_date)

        for component_code, rule_code in expected_rules.items():
            if component_code not in components_by_code:
                continue
            if rule_sets_by_code[rule_code] is None:
                checks.append(
                    ValidationCheckDTO(
                        check_code="MISSING_RULE_SET",
                        category="rules",
                        severity="warning",
                        title="Missing Rule Set",
                        message=(
                            f"Rule set '{rule_code}' (for component '{component_code}') is not configured or not effective "
                            f"for {period_date.year}-{period_date.month:02d}. Provisional fallback rates will be used."
                        ),
                        entity_type="payroll_rule_set",
                        entity_label=rule_code,
                    )
                )

        for rule_set in rule_sets:
            issues: list[str] = []
            if not rule_set.brackets:
                issues.append("no bracket rows configured")
            for bracket in rule_set.brackets:
                if (
                    bracket.lower_bound_amount is not None
                    and bracket.upper_bound_amount is not None
                    and bracket.upper_bound_amount <= bracket.lower_bound_amount
                ):
                    issues.append(f"line {bracket.line_number} upper bound is not greater than lower bound")
                if all(
                    value in (None, Decimal("0"))
                    for value in (
                        bracket.rate_percent,
                        bracket.fixed_amount,
                        bracket.deduction_amount,
                    )
                ) and bracket.cap_amount is None:
                    issues.append(f"line {bracket.line_number} has no usable rate or amount")
                if any(
                    value is not None and Decimal(str(value)) < Decimal("0")
                    for value in (
                        bracket.rate_percent,
                        bracket.fixed_amount,
                        bracket.deduction_amount,
                        bracket.cap_amount,
                    )
                ):
                    issues.append(f"line {bracket.line_number} contains negative values")
            if issues:
                checks.append(
                    ValidationCheckDTO(
                        check_code="INVALID_OR_MISSING_RULE_BRACKETS",
                        category="rules",
                        severity="error",
                        title="Invalid or Missing Rule Brackets",
                        message=f"Rule set '{rule_set.rule_code}' has invalid bracket configuration: {issues[0]}.",
                        entity_type="payroll_rule_set",
                        entity_id=rule_set.id,
                        entity_label=rule_set.rule_code,
                    )
                )

        overtime_quantity_inputs = [
            line
            for batch in input_batches
            for line in batch.lines
            if line.component and line.component.component_code == "OVERTIME"
            and line.input_quantity is not None
            and Decimal(str(line.input_quantity)) > Decimal("0")
        ]
        if overtime_quantity_inputs and rule_sets_by_code.get("OVERTIME_STANDARD") is None:
            checks.append(
                ValidationCheckDTO(
                    check_code="MISSING_OVERTIME_RULE_LINK",
                    category="rules",
                    severity="warning",
                    title="Missing Overtime Rule Link",
                    message=(
                        "Approved overtime quantity inputs exist for this period, but rule set 'OVERTIME_STANDARD' "
                        "is not configured. The overtime engine will fall back to its default multiplier."
                    ),
                    entity_type="payroll_rule_set",
                    entity_label="OVERTIME_STANDARD",
                )
            )

        if any(component.component_code in _BIK_CODES for component in components):
            if settings is None or not settings.benefit_in_kind_policy_mode_code:
                checks.append(
                    ValidationCheckDTO(
                        check_code="BENEFITS_IN_KIND_SETUP_ISSUE",
                        category="setup",
                        severity="warning",
                        title="Benefits-in-Kind Policy Missing",
                        message=(
                            "Benefits-in-kind components exist, but no benefits-in-kind policy mode is configured in payroll settings."
                        ),
                    )
                )

        # ── Statutory compliance: DGI IRPP abattement ────────────────────────
        if rule_sets_by_code.get("DGI_IRPP_ABATTEMENT") is None:
            checks.append(
                ValidationCheckDTO(
                    check_code="MISSING_RULE_SET",
                    category="rules",
                    severity="warning",
                    title="Missing IRPP Abattement Rule Set",
                    message=(
                        "Rule set 'DGI_IRPP_ABATTEMENT' is not configured. The system will use provisional "
                        "fallback values (30 % abattement + 500,000 XAF annual minimum vital deduction). "
                        "Apply the statutory pack to seed this rule set."
                    ),
                    entity_type="payroll_rule_set",
                    entity_label="DGI_IRPP_ABATTEMENT",
                )
            )

        # ── Statutory compliance: CNPS employer rate verification ─────────────
        cnps_er_rs = rule_sets_by_code.get("CNPS_EMPLOYER_MAIN")
        if cnps_er_rs is not None and cnps_er_rs.brackets:
            first_bracket = cnps_er_rs.brackets[0]
            if first_bracket.rate_percent is not None:
                rate_val = Decimal(str(first_bracket.rate_percent))
                if rate_val > Decimal("4.20") + Decimal("0.01"):
                    checks.append(
                        ValidationCheckDTO(
                            check_code="CNPS_EMPLOYER_RATE_MISMATCH",
                            category="rules",
                            severity="error",
                            title="CNPS Employer Rate Possibly Incorrect",
                            message=(
                                f"CNPS_EMPLOYER_MAIN first bracket rate is {rate_val} %. "
                                "The correct CNPS employer PVID rate is 4.20 % (total PVID 8.40 % split equally). "
                                "Re-apply the statutory pack or correct the rule set manually."
                            ),
                            entity_type="payroll_rule_set",
                            entity_id=cnps_er_rs.id,
                            entity_label="CNPS_EMPLOYER_MAIN",
                        )
                    )

        return rule_sets_by_code

    def _append_fallback_reliance_check(
        self,
        checks: list[ValidationCheckDTO],
        components: list,
        rule_sets_by_code: dict[str, object | None],
        input_batches: list,
    ) -> None:
        reasons: list[str] = []
        component_codes = {component.component_code for component in components}
        fallback_map = {
            "EMPLOYEE_CNPS": "CNPS_EMPLOYEE_MAIN",
            "EMPLOYER_CNPS": "CNPS_EMPLOYER_MAIN",
            "ACCIDENT_RISK_EMPLOYER": "ACCIDENT_RISK_STANDARD",
            "CFC_HLF": "CCF_MAIN",
            "FNE_EMPLOYEE": "FNE_EMPLOYEE_MAIN",
            "FNE": "FNE_EMPLOYER_MAIN",
            "EMPLOYER_AF": "AF_MAIN",
        }
        for component_code, rule_code in fallback_map.items():
            if component_code in component_codes and rule_sets_by_code.get(rule_code) is None:
                reasons.append(f"{rule_code} is missing")

        overtime_quantity_inputs = any(
            line.component and line.component.component_code == "OVERTIME"
            and line.input_quantity is not None
            and Decimal(str(line.input_quantity)) > Decimal("0")
            for batch in input_batches
            for line in batch.lines
        )
        if overtime_quantity_inputs and rule_sets_by_code.get("OVERTIME_STANDARD") is None:
            reasons.append("OVERTIME_STANDARD is missing while overtime quantity inputs exist")

        if reasons:
            checks.append(
                ValidationCheckDTO(
                    check_code="FALLBACK_STATUTORY_CONSTANTS_RELIANCE",
                    category="rules",
                    severity="warning",
                    title="Fallback Statutory Constants In Use",
                    message=(
                        "Current payroll configuration would fall back to hard-coded statutory constants because "
                        + "; ".join(reasons)
                        + "."
                    ),
                )
            )

    def _append_payment_consistency_checks(
        self,
        checks: list[ValidationCheckDTO],
        company_id: int,
        run_repo: PayrollRunRepository,
        run_employee_repo: PayrollRunEmployeeRepository,
        payment_repo: PayrollPaymentRecordRepository,
    ) -> None:
        posted_runs = run_repo.list_by_company(company_id, status_code="posted")
        for run in posted_runs:
            payments_by_employee: dict[int, list] = defaultdict(list)
            for record in payment_repo.list_by_run(company_id, run.id):
                payments_by_employee[record.run_employee_id].append(record)

            for employee_row in run_employee_repo.list_by_run(company_id, run.id):
                if employee_row.status_code != "included":
                    continue
                records = payments_by_employee.get(employee_row.id, [])
                total_paid = sum((Decimal(str(record.amount_paid)) for record in records), Decimal("0"))
                net_payable = Decimal(str(employee_row.net_payable))
                if total_paid > net_payable + _TOLERANCE:
                    checks.append(
                        ValidationCheckDTO(
                            check_code="PAYMENT_INCONSISTENCY",
                            category="payments",
                            severity="error",
                            title="Employee Payment Overpaid",
                            message=(
                                f"Run '{run.run_reference}' employee '{employee_row.employee.display_name if employee_row.employee else employee_row.employee_id}' "
                                "has payments recorded above net payable."
                            ),
                            entity_type="payroll_run_employee",
                            entity_id=employee_row.id,
                            entity_label=employee_row.employee.display_name if employee_row.employee else None,
                        )
                    )
                elif records:
                    expected_status = (
                        "unpaid"
                        if total_paid <= _TOLERANCE
                        else "paid"
                        if total_paid >= net_payable - _TOLERANCE
                        else "partial"
                    )
                    if employee_row.payment_status_code != expected_status:
                        checks.append(
                            ValidationCheckDTO(
                                check_code="PAYMENT_INCONSISTENCY",
                                category="payments",
                                severity="warning",
                                title="Employee Payment Status Mismatch",
                                message=(
                                    f"Run '{run.run_reference}' employee '{employee_row.employee.display_name if employee_row.employee else employee_row.employee_id}' "
                                    f"has payment status '{employee_row.payment_status_code}' but totals indicate '{expected_status}'."
                                ),
                                entity_type="payroll_run_employee",
                                entity_id=employee_row.id,
                                entity_label=employee_row.employee.display_name if employee_row.employee else None,
                            )
                        )

    def _append_remittance_consistency_checks(
        self,
        checks: list[ValidationCheckDTO],
        company_id: int,
        remittance_repo: PayrollRemittanceBatchRepository,
    ) -> None:
        for batch in remittance_repo.list_by_company(company_id):
            batch = remittance_repo.get_by_id(company_id, batch.id) or batch
            due = Decimal(str(batch.amount_due))
            paid = Decimal(str(batch.amount_paid))
            if paid > due + _TOLERANCE:
                checks.append(
                    ValidationCheckDTO(
                        check_code="REMITTANCE_INCONSISTENCY",
                        category="remittances",
                        severity="error",
                        title="Remittance Batch Overpaid",
                        message=f"Remittance batch '{batch.batch_number}' is paid above its due amount.",
                        entity_type="payroll_remittance_batch",
                        entity_id=batch.id,
                        entity_label=batch.batch_number,
                    )
                )
            elif batch.status_code == "paid" and paid < due - _TOLERANCE:
                checks.append(
                    ValidationCheckDTO(
                        check_code="REMITTANCE_INCONSISTENCY",
                        category="remittances",
                        severity="warning",
                        title="Remittance Batch Status Mismatch",
                        message=f"Remittance batch '{batch.batch_number}' is marked paid but still has outstanding balance.",
                        entity_type="payroll_remittance_batch",
                        entity_id=batch.id,
                        entity_label=batch.batch_number,
                    )
                )

            for line in getattr(batch, "lines", []):
                line_due = Decimal(str(line.amount_due))
                line_paid = Decimal(str(line.amount_paid))
                if line_paid > line_due + _TOLERANCE:
                    checks.append(
                        ValidationCheckDTO(
                            check_code="REMITTANCE_INCONSISTENCY",
                            category="remittances",
                            severity="error",
                            title="Remittance Line Overpaid",
                            message=(
                                f"Remittance batch '{batch.batch_number}' line {line.line_number} is paid above its due amount."
                            ),
                            entity_type="payroll_remittance_line",
                            entity_id=line.id,
                            entity_label=str(line.line_number),
                        )
                    )
                elif line.status_code == "paid" and line_paid < line_due - _TOLERANCE:
                    checks.append(
                        ValidationCheckDTO(
                            check_code="REMITTANCE_INCONSISTENCY",
                            category="remittances",
                            severity="warning",
                            title="Remittance Line Status Mismatch",
                            message=(
                                f"Remittance batch '{batch.batch_number}' line {line.line_number} is marked paid but still has outstanding balance."
                            ),
                            entity_type="payroll_remittance_line",
                            entity_id=line.id,
                            entity_label=str(line.line_number),
                        )
                    )

    @staticmethod
    def _covers_period(record, period_date: date) -> bool:
        if record.effective_from > period_date:
            return False
        return record.effective_to is None or record.effective_to >= period_date

    @staticmethod
    def _ranges_overlap(
        left_start: date,
        left_end: date | None,
        right_start: date,
        right_end: date | None,
    ) -> bool:
        left_last = left_end or date.max
        right_last = right_end or date.max
        return left_start <= right_last and right_start <= left_last
