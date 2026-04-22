"""PayrollPostingValidationService — pre-posting validation for payroll runs.

Validates:
  - Run exists, belongs to company, and is eligible for posting (approved status)
  - Run has included employee lines
  - Fiscal period is open for the proposed posting date
  - All components used in the run have required account mappings
  - The payroll_payable role is mapped for the company
  - All posting accounts are active and allow posting

Returns a PayrollPostingValidationResultDTO with blocking errors and warnings.
Does NOT modify any data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from sqlalchemy import select
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
from seeker_accounting.modules.payroll.dto.payroll_posting_dto import (
    PayrollPostingValidationIssueDTO,
    PayrollPostingValidationResultDTO,
)
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_run import PayrollRun
from seeker_accounting.modules.payroll.models.payroll_run_employee import PayrollRunEmployee
from seeker_accounting.modules.payroll.models.payroll_run_line import PayrollRunLine
from seeker_accounting.modules.payroll.repositories.payroll_run_repository import (
    PayrollRunRepository,
)
from seeker_accounting.platform.exceptions import NotFoundError

_CALENDAR_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

_PAYROLL_PAYABLE_ROLE = "payroll_payable"

# Component types that require an expense_account_id on the debit side
_DEBIT_TYPES = frozenset({"earning", "employer_contribution"})
# Component types that require a liability_account_id on the credit side
_CREDIT_TYPES = frozenset({"deduction", "tax", "employer_contribution"})


class PayrollPostingValidationService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        run_repository_factory: Callable[[Session], PayrollRunRepository],
        account_repository_factory: Callable[[Session], AccountRepository],
        fiscal_period_repository_factory: Callable[[Session], FiscalPeriodRepository],
        account_role_mapping_repository_factory: Callable[
            [Session], AccountRoleMappingRepository
        ],
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._run_repo_factory = run_repository_factory
        self._account_repo_factory = account_repository_factory
        self._period_repo_factory = fiscal_period_repository_factory
        self._role_mapping_repo_factory = account_role_mapping_repository_factory

    def validate(
        self,
        company_id: int,
        run_id: int,
        posting_date: date,
    ) -> PayrollPostingValidationResultDTO:
        issues: list[PayrollPostingValidationIssueDTO] = []

        with self._uow_factory() as uow:
            run_repo = self._run_repo_factory(uow.session)
            run = run_repo.get_by_id(company_id, run_id)
            if run is None:
                raise NotFoundError("Payroll run not found.")

            period_label = f"{_CALENDAR_MONTHS[run.period_month]} {run.period_year}"

            # 1. Status check
            if run.status_code == "posted":
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="ALREADY_POSTED",
                    message="This payroll run has already been posted to the GL.",
                    severity="error",
                ))
            elif run.status_code not in ("approved", "calculated"):
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="INVALID_STATUS",
                    message=(
                        f"Run status is '{run.status_code}'. "
                        "Only approved (or calculated) runs can be posted."
                    ),
                    severity="error",
                ))

            if run.status_code == "calculated":
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="NOT_APPROVED",
                    message="Run has not been formally approved. Posting a calculated run directly is allowed but skips the approval step.",
                    severity="warning",
                ))

            # 2. Employee coverage check
            employees = self._load_included_employees(uow.session, company_id, run_id)
            if not employees:
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="NO_EMPLOYEES",
                    message="No included employees found in this run. Nothing to post.",
                    severity="error",
                ))
            else:
                # 3. Account mapping validation per component
                self._validate_component_accounts(
                    uow.session, company_id, run_id, issues
                )

            # 4. Net salary payable role mapping
            role_repo = self._role_mapping_repo_factory(uow.session)
            payroll_payable_mapping = role_repo.get_by_role_code(
                company_id, _PAYROLL_PAYABLE_ROLE
            )
            if payroll_payable_mapping is None:
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="NO_PAYROLL_PAYABLE_ACCOUNT",
                    message=(
                        "The 'Payroll Payable' account role is not mapped for this company. "
                        "Configure it in Accounting Setup → Account Role Mappings."
                    ),
                    severity="error",
                ))
            else:
                acct_repo = self._account_repo_factory(uow.session)
                acct = acct_repo.get_by_id(company_id, payroll_payable_mapping.account_id)
                if acct is None or not acct.is_active:
                    issues.append(PayrollPostingValidationIssueDTO(
                        issue_code="PAYROLL_PAYABLE_INACTIVE",
                        message="The mapped 'Payroll Payable' account is inactive.",
                        severity="error",
                    ))
                elif not acct.allow_manual_posting:
                    issues.append(PayrollPostingValidationIssueDTO(
                        issue_code="PAYROLL_PAYABLE_CONTROL_ACCOUNT",
                        message=(
                            "The mapped 'Payroll Payable' account does not allow posting "
                            "(it is a control-only account). Use a posting-allowed account."
                        ),
                        severity="error",
                    ))

            # 5. Fiscal period check
            period_repo = self._period_repo_factory(uow.session)
            fiscal_period = period_repo.get_covering_date(company_id, posting_date)
            if fiscal_period is None:
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="NO_FISCAL_PERIOD",
                    message=(
                        f"No fiscal period covers the posting date {posting_date}. "
                        "Create or extend a fiscal period to include this date."
                    ),
                    severity="error",
                ))
            elif fiscal_period.status_code == "LOCKED":
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="PERIOD_LOCKED",
                    message=f"Fiscal period '{fiscal_period.period_code}' is locked. Posting is not allowed.",
                    severity="error",
                ))
            elif fiscal_period.status_code != "OPEN":
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="PERIOD_NOT_OPEN",
                    message=f"Fiscal period '{fiscal_period.period_code}' is not open for posting.",
                    severity="error",
                ))

        has_errors = any(i.severity == "error" for i in issues)
        return PayrollPostingValidationResultDTO(
            run_id=run_id,
            run_reference=run.run_reference,
            period_label=period_label,
            has_errors=has_errors,
            issues=tuple(issues),
        )

    def _load_included_employees(
        self, session: Session, company_id: int, run_id: int
    ) -> list[PayrollRunEmployee]:
        stmt = select(PayrollRunEmployee).where(
            PayrollRunEmployee.company_id == company_id,
            PayrollRunEmployee.run_id == run_id,
            PayrollRunEmployee.status_code == "included",
        )
        return list(session.scalars(stmt).all())

    def _validate_component_accounts(
        self,
        session: Session,
        company_id: int,
        run_id: int,
        issues: list[PayrollPostingValidationIssueDTO],
    ) -> None:
        """Check that every component used in the run has proper account mappings."""
        stmt = (
            select(PayrollRunLine.component_id, PayrollRunLine.component_type_code)
            .join(PayrollRunEmployee, PayrollRunLine.run_employee_id == PayrollRunEmployee.id)
            .where(
                PayrollRunLine.run_id == run_id,
                PayrollRunEmployee.status_code == "included",
                PayrollRunLine.component_type_code != "informational",
            )
            .distinct()
        )
        component_rows = session.execute(stmt).all()
        if not component_rows:
            return

        component_ids = [r.component_id for r in component_rows]
        comp_stmt = select(PayrollComponent).where(
            PayrollComponent.id.in_(component_ids),
            PayrollComponent.company_id == company_id,
        )
        components_by_id = {c.id: c for c in session.scalars(comp_stmt).all()}

        acct_repo_raw = AccountRepository(session)

        for row in component_rows:
            comp = components_by_id.get(row.component_id)
            if comp is None:
                issues.append(PayrollPostingValidationIssueDTO(
                    issue_code="COMPONENT_NOT_FOUND",
                    message=f"Component id={row.component_id} not found in this company.",
                    severity="error",
                ))
                continue

            if row.component_type_code in _DEBIT_TYPES:
                if comp.expense_account_id is None:
                    issues.append(PayrollPostingValidationIssueDTO(
                        issue_code="MISSING_EXPENSE_ACCOUNT",
                        message=(
                            f"Component '{comp.component_code}' ({row.component_type_code}) "
                            "has no expense account mapped. Configure it in Payroll → Components."
                        ),
                        severity="error",
                    ))
                else:
                    acct = acct_repo_raw.get_by_id(company_id, comp.expense_account_id)
                    if acct is None or not acct.is_active or not acct.allow_manual_posting:
                        issues.append(PayrollPostingValidationIssueDTO(
                            issue_code="EXPENSE_ACCOUNT_INVALID",
                            message=(
                                f"Component '{comp.component_code}' expense account is inactive "
                                "or does not allow posting."
                            ),
                            severity="error",
                        ))

            if row.component_type_code in _CREDIT_TYPES:
                if comp.liability_account_id is None:
                    issues.append(PayrollPostingValidationIssueDTO(
                        issue_code="MISSING_LIABILITY_ACCOUNT",
                        message=(
                            f"Component '{comp.component_code}' ({row.component_type_code}) "
                            "has no liability account mapped. Configure it in Payroll → Components."
                        ),
                        severity="error",
                    ))
                else:
                    acct = acct_repo_raw.get_by_id(company_id, comp.liability_account_id)
                    if acct is None or not acct.is_active or not acct.allow_manual_posting:
                        issues.append(PayrollPostingValidationIssueDTO(
                            issue_code="LIABILITY_ACCOUNT_INVALID",
                            message=(
                                f"Component '{comp.component_code}' liability account is inactive "
                                "or does not allow posting."
                            ),
                            severity="error",
                        ))
