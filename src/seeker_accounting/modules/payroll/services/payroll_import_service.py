"""Payroll Import Service — preview-first CSV imports for payroll master data.

Imports are additive and company-scoped. Existing rows are skipped; no import
path overwrites existing payroll setup truth.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.accounting.chart_of_accounts.repositories.account_repository import (
    AccountRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.currency_repository import (
    CurrencyRepository,
)
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.payroll_import_dto import (
    ImportPreviewResultDTO,
    ImportPreviewRowDTO,
    ImportResultDTO,
    ImportRowIssueDTO,
)
from seeker_accounting.modules.payroll.models.department import Department
from seeker_accounting.modules.payroll.models.employee import Employee
from seeker_accounting.modules.payroll.models.employee_component_assignment import (
    EmployeeComponentAssignment,
)
from seeker_accounting.modules.payroll.models.employee_compensation_profile import (
    EmployeeCompensationProfile,
)
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet
from seeker_accounting.modules.payroll.models.position import Position
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_IMPORT
from seeker_accounting.modules.payroll.repositories.compensation_profile_repository import (
    CompensationProfileRepository,
)
from seeker_accounting.modules.payroll.repositories.component_assignment_repository import (
    ComponentAssignmentRepository,
)
from seeker_accounting.modules.payroll.repositories.department_repository import DepartmentRepository
from seeker_accounting.modules.payroll.repositories.employee_repository import EmployeeRepository
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import (
    PayrollRuleSetRepository,
)
from seeker_accounting.modules.payroll.repositories.position_repository import PositionRepository
from seeker_accounting.modules.payroll.services.payroll_component_service import (
    _VALID_CALCULATION_METHODS,
    _VALID_COMPONENT_TYPES,
)
from seeker_accounting.modules.payroll.services.payroll_rule_service import (
    _VALID_CALCULATION_BASES,
    _VALID_RULE_TYPES,
)
from seeker_accounting.platform.exceptions import ValidationError

DepartmentRepositoryFactory = Callable[[Session], DepartmentRepository]
PositionRepositoryFactory = Callable[[Session], PositionRepository]
EmployeeRepositoryFactory = Callable[[Session], EmployeeRepository]
PayrollComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]
PayrollRuleSetRepositoryFactory = Callable[[Session], PayrollRuleSetRepository]
CompensationProfileRepositoryFactory = Callable[[Session], CompensationProfileRepository]
ComponentAssignmentRepositoryFactory = Callable[[Session], ComponentAssignmentRepository]
AccountRepositoryFactory = Callable[[Session], AccountRepository]
CurrencyRepositoryFactory = Callable[[Session], CurrencyRepository]

_DEPARTMENT_COLUMNS = ("code", "name", "is_active")
_POSITION_COLUMNS = ("code", "title", "is_active")
_EMPLOYEE_COLUMNS = (
    "employee_number",
    "first_name",
    "last_name",
    "hire_date",
    "department_code",
    "position_code",
    "is_active",
)
_COMPONENT_COLUMNS = (
    "component_code",
    "component_name",
    "component_type_code",
    "calculation_method_code",
    "is_taxable",
    "is_pensionable",
    "expense_account_code",
    "liability_account_code",
    "is_active",
)
_RULE_SET_COLUMNS = (
    "rule_code",
    "rule_name",
    "rule_type_code",
    "calculation_basis_code",
    "effective_from",
    "effective_to",
    "is_active",
)
_RULE_BRACKET_COLUMNS = (
    "rule_code",
    "effective_from",
    "line_number",
    "lower_bound_amount",
    "upper_bound_amount",
    "rate_percent",
    "fixed_amount",
    "deduction_amount",
    "cap_amount",
)
_PROFILE_COLUMNS = (
    "employee_number",
    "profile_name",
    "basic_salary",
    "currency_code",
    "effective_from",
    "effective_to",
    "notes",
    "is_active",
)
_ASSIGNMENT_COLUMNS = (
    "employee_number",
    "component_code",
    "override_amount",
    "override_rate",
    "effective_from",
    "effective_to",
    "is_active",
)


@dataclass(slots=True)
class _ImportContext:
    department_repo: DepartmentRepository
    position_repo: PositionRepository
    employee_repo: EmployeeRepository
    component_repo: PayrollComponentRepository
    rule_set_repo: PayrollRuleSetRepository
    profile_repo: CompensationProfileRepository
    assignment_repo: ComponentAssignmentRepository
    account_repo: AccountRepository
    currency_repo: CurrencyRepository


class PayrollImportService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        department_repo_factory: DepartmentRepositoryFactory,
        position_repo_factory: PositionRepositoryFactory,
        employee_repo_factory: EmployeeRepositoryFactory,
        component_repo_factory: PayrollComponentRepositoryFactory,
        rule_set_repo_factory: PayrollRuleSetRepositoryFactory,
        profile_repo_factory: CompensationProfileRepositoryFactory,
        assignment_repo_factory: ComponentAssignmentRepositoryFactory,
        account_repo_factory: AccountRepositoryFactory,
        currency_repo_factory: CurrencyRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._dept_repo_factory = department_repo_factory
        self._pos_repo_factory = position_repo_factory
        self._emp_repo_factory = employee_repo_factory
        self._component_repo_factory = component_repo_factory
        self._rule_set_repo_factory = rule_set_repo_factory
        self._profile_repo_factory = profile_repo_factory
        self._assignment_repo_factory = assignment_repo_factory
        self._account_repo_factory = account_repo_factory
        self._currency_repo_factory = currency_repo_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def preview(
        self, company_id: int, entity_type: str, file_path: str
    ) -> ImportPreviewResultDTO:
        self._permission_service.require_permission(PAYROLL_IMPORT)
        expected = self._expected_columns(entity_type)
        rows = self._read_csv(file_path)
        if not rows:
            raise ValidationError("CSV file is empty or has no data rows.")

        columns_found = tuple(rows[0].keys()) if rows else ()
        self._validate_headers(self._required_columns(entity_type), columns_found)

        preview_rows: list[ImportPreviewRowDTO] = []
        valid = warning = error = 0

        with self._uow_factory() as uow:
            context = self._build_context(uow.session)
            for index, row in enumerate(rows, start=2):
                issues = tuple(self._validate_row(context, company_id, entity_type, row, index))
                preview = ImportPreviewRowDTO(row_number=index, values=dict(row), issues=issues)
                preview_rows.append(preview)
                if preview.has_errors:
                    error += 1
                elif issues:
                    warning += 1
                else:
                    valid += 1

        return ImportPreviewResultDTO(
            entity_type=entity_type,
            file_path=file_path,
            total_rows=len(rows),
            valid_rows=valid,
            error_rows=error,
            warning_rows=warning,
            columns_found=columns_found,
            columns_expected=expected,
            preview_rows=tuple(preview_rows[:100]),
        )

    def execute_import(
        self, company_id: int, entity_type: str, file_path: str
    ) -> ImportResultDTO:
        self._permission_service.require_permission(PAYROLL_IMPORT)
        rows = self._read_csv(file_path)
        if not rows:
            raise ValidationError("CSV file is empty.")

        expected = self._expected_columns(entity_type)
        columns_found = tuple(rows[0].keys()) if rows else ()
        self._validate_headers(self._required_columns(entity_type), columns_found)

        with self._uow_factory() as uow:
            context = self._build_context(uow.session)
            result = self._execute_rows(uow.session, context, company_id, entity_type, rows)
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_IMPORT_EXECUTED",
                    module_code="payroll",
                    entity_type=entity_type,
                    entity_id=None,
                    description=f"Executed payroll import for '{entity_type}'.",
                    detail_json=json.dumps(
                        {
                            "entity_type": entity_type,
                            "total_rows": result.total_rows,
                            "created": result.created,
                            "skipped": result.skipped,
                            "errors": result.errors,
                        }
                    ),
                ),
            )
            uow.commit()
            return result

    def _execute_rows(
        self,
        session: Session,
        context: _ImportContext,
        company_id: int,
        entity_type: str,
        rows: list[dict[str, str]],
    ) -> ImportResultDTO:
        handler_map = {
            "departments": self._create_department,
            "positions": self._create_position,
            "employees": self._create_employee,
            "payroll_components": self._create_component,
            "payroll_rule_sets": self._create_rule_set,
            "payroll_rule_brackets": self._create_rule_bracket,
            "employee_compensation_profiles": self._create_profile,
            "employee_component_assignments": self._create_assignment,
        }
        handler = handler_map.get(entity_type)
        if handler is None:
            raise ValidationError(f"Unsupported import type: '{entity_type}'.")

        created = skipped = errors = 0
        messages: list[str] = []
        for index, row in enumerate(rows, start=2):
            issues = self._validate_row(context, company_id, entity_type, row, index)
            row_errors = [issue for issue in issues if issue.severity == "error"]
            if row_errors:
                errors += 1
                messages.append(f"Row {index}: {row_errors[0].message}")
                continue

            outcome, message = handler(context, company_id, row)
            if outcome == "created":
                created += 1
            elif outcome == "skipped":
                skipped += 1
            else:
                errors += 1
            if message:
                messages.append(f"Row {index}: {message}")

        return ImportResultDTO(
            entity_type=entity_type,
            total_rows=len(rows),
            created=created,
            skipped=skipped,
            errors=errors,
            messages=tuple(messages),
        )

    def _validate_row(
        self,
        context: _ImportContext,
        company_id: int,
        entity_type: str,
        row: dict[str, str],
        row_num: int,
    ) -> list[ImportRowIssueDTO]:
        issues: list[ImportRowIssueDTO] = []

        def add(column: str, message: str, severity: str = "error") -> None:
            issues.append(ImportRowIssueDTO(row_num, column, message, severity))

        if entity_type == "departments":
            code = self._required_code(row, "code", add)
            name = self._required_text(row, "name", add)
            if code and context.department_repo.get_by_code(company_id, code) is not None:
                add("code", f"Department '{code}' already exists and will be skipped.", "warning")
            return issues

        if entity_type == "positions":
            code = self._required_code(row, "code", add)
            title = self._required_text(row, "title", add)
            if code and context.position_repo.get_by_code(company_id, code) is not None:
                add("code", f"Position '{code}' already exists and will be skipped.", "warning")
            return issues

        if entity_type == "employees":
            employee_number = self._required_code(row, "employee_number", add)
            self._required_text(row, "first_name", add)
            self._required_text(row, "last_name", add)
            hire_date = self._parse_required_date(row, "hire_date", add)
            if employee_number and context.employee_repo.get_by_number(company_id, employee_number) is not None:
                add("employee_number", f"Employee '{employee_number}' already exists and will be skipped.", "warning")
            department_code = self._normalize_code(row.get("department_code"))
            if department_code and context.department_repo.get_by_code(company_id, department_code) is None:
                add("department_code", f"Department '{department_code}' was not found and assignment will be skipped.", "warning")
            position_code = self._normalize_code(row.get("position_code"))
            if position_code and context.position_repo.get_by_code(company_id, position_code) is None:
                add("position_code", f"Position '{position_code}' was not found and assignment will be skipped.", "warning")
            return issues

        if entity_type == "payroll_components":
            component_code = self._required_code(row, "component_code", add)
            self._required_text(row, "component_name", add)
            component_type_code = self._required_text(row, "component_type_code", add)
            calc_method = self._required_text(row, "calculation_method_code", add)
            if component_type_code and component_type_code not in _VALID_COMPONENT_TYPES:
                add("component_type_code", f"Invalid component type '{component_type_code}'.")
            if calc_method and calc_method not in _VALID_CALCULATION_METHODS:
                add("calculation_method_code", f"Invalid calculation method '{calc_method}'.")
            self._parse_bool(row.get("is_taxable"), "is_taxable", add)
            self._parse_bool(row.get("is_pensionable"), "is_pensionable", add)
            self._parse_bool(row.get("is_active"), "is_active", add)
            expense_account_code = self._normalize_code(row.get("expense_account_code"))
            if expense_account_code and context.account_repo.get_by_code(company_id, expense_account_code) is None:
                add("expense_account_code", f"Account '{expense_account_code}' was not found.")
            liability_account_code = self._normalize_code(row.get("liability_account_code"))
            if liability_account_code and context.account_repo.get_by_code(company_id, liability_account_code) is None:
                add("liability_account_code", f"Account '{liability_account_code}' was not found.")
            if component_code and context.component_repo.get_by_code(company_id, component_code) is not None:
                add("component_code", f"Component '{component_code}' already exists and will be skipped.", "warning")
            return issues

        if entity_type == "payroll_rule_sets":
            rule_code = self._required_code(row, "rule_code", add)
            self._required_text(row, "rule_name", add)
            rule_type_code = self._required_text(row, "rule_type_code", add)
            calc_basis = self._required_text(row, "calculation_basis_code", add)
            effective_from = self._parse_required_date(row, "effective_from", add)
            effective_to = self._parse_optional_date(row, "effective_to", add)
            self._parse_bool(row.get("is_active"), "is_active", add)
            if rule_type_code and rule_type_code not in _VALID_RULE_TYPES:
                add("rule_type_code", f"Invalid rule type '{rule_type_code}'.")
            if calc_basis and calc_basis not in _VALID_CALCULATION_BASES:
                add("calculation_basis_code", f"Invalid calculation basis '{calc_basis}'.")
            if effective_from and effective_to and effective_to < effective_from:
                add("effective_to", "Effective-to date cannot be before effective-from date.")
            if rule_code and effective_from and context.rule_set_repo.get_by_code_and_date(company_id, rule_code, effective_from) is not None:
                add("rule_code", f"Rule set '{rule_code}' with date {effective_from} already exists and will be skipped.", "warning")
            return issues

        if entity_type == "payroll_rule_brackets":
            rule_code = self._required_code(row, "rule_code", add)
            effective_from = self._parse_required_date(row, "effective_from", add)
            line_number = self._parse_required_int(row, "line_number", add)
            lower_bound = self._parse_optional_decimal(row, "lower_bound_amount", add)
            upper_bound = self._parse_optional_decimal(row, "upper_bound_amount", add)
            rate_percent = self._parse_optional_decimal(row, "rate_percent", add)
            fixed_amount = self._parse_optional_decimal(row, "fixed_amount", add)
            deduction_amount = self._parse_optional_decimal(row, "deduction_amount", add)
            cap_amount = self._parse_optional_decimal(row, "cap_amount", add)
            if lower_bound is not None and upper_bound is not None and upper_bound <= lower_bound:
                add("upper_bound_amount", "Upper bound must be greater than lower bound.")
            if all(value is None for value in (rate_percent, fixed_amount, deduction_amount, cap_amount)):
                add("rate_percent", "At least one rate or amount value is required.")
            if rule_code and effective_from:
                rule_set = context.rule_set_repo.get_by_code_and_date(company_id, rule_code, effective_from)
                if rule_set is None:
                    add("rule_code", f"Rule set '{rule_code}' effective {effective_from} was not found.")
                elif line_number and context.rule_set_repo.get_bracket(rule_set.id, line_number) is not None:
                    add("line_number", f"Bracket line {line_number} already exists and will be skipped.", "warning")
            return issues

        if entity_type == "employee_compensation_profiles":
            employee_number = self._required_code(row, "employee_number", add)
            self._required_text(row, "profile_name", add)
            basic_salary = self._parse_required_decimal(row, "basic_salary", add)
            currency_code = self._required_code(row, "currency_code", add)
            effective_from = self._parse_required_date(row, "effective_from", add)
            effective_to = self._parse_optional_date(row, "effective_to", add)
            self._parse_bool(row.get("is_active"), "is_active", add)
            if basic_salary is not None and basic_salary <= Decimal("0"):
                add("basic_salary", "Basic salary must be greater than zero.")
            if effective_from and effective_to and effective_to <= effective_from:
                add("effective_to", "Effective-to date must be after effective-from date.")
            employee = context.employee_repo.get_by_number(company_id, employee_number) if employee_number else None
            if employee_number and employee is None:
                add("employee_number", f"Employee '{employee_number}' was not found.")
            if currency_code and not context.currency_repo.exists_active(currency_code):
                add("currency_code", f"Currency '{currency_code}' was not found or is inactive.")
            if employee and effective_from and context.profile_repo.check_duplicate(company_id, employee.id, effective_from):
                add("effective_from", f"Compensation profile for employee '{employee_number}' on {effective_from} already exists and will be skipped.", "warning")
            return issues

        if entity_type == "employee_component_assignments":
            employee_number = self._required_code(row, "employee_number", add)
            component_code = self._required_code(row, "component_code", add)
            override_amount = self._parse_optional_decimal(row, "override_amount", add)
            override_rate = self._parse_optional_decimal(row, "override_rate", add)
            effective_from = self._parse_required_date(row, "effective_from", add)
            effective_to = self._parse_optional_date(row, "effective_to", add)
            self._parse_bool(row.get("is_active"), "is_active", add)
            if effective_from and effective_to and effective_to <= effective_from:
                add("effective_to", "Effective-to date must be after effective-from date.")
            employee = context.employee_repo.get_by_number(company_id, employee_number) if employee_number else None
            if employee_number and employee is None:
                add("employee_number", f"Employee '{employee_number}' was not found.")
            component = context.component_repo.get_by_code(company_id, component_code) if component_code else None
            if component_code and component is None:
                add("component_code", f"Component '{component_code}' was not found.")
            if employee and component and effective_from and context.assignment_repo.check_duplicate(company_id, employee.id, component.id, effective_from):
                add("effective_from", f"Assignment for employee '{employee_number}' and component '{component_code}' already exists and will be skipped.", "warning")
            return issues

        raise ValidationError(f"Unsupported import type: '{entity_type}'.")

    def _create_department(self, context: _ImportContext, company_id: int, row: dict[str, str]) -> tuple[str, str | None]:
        code = self._normalize_code(row.get("code"))
        if context.department_repo.get_by_code(company_id, code) is not None:
            return "skipped", f"Department '{code}' already exists."
        now = datetime.utcnow()
        context.department_repo.save(
            Department(
                company_id=company_id,
                code=code,
                name=row.get("name", "").strip(),
                is_active=self._parse_bool_value(row.get("is_active"), True),
                created_at=now,
                updated_at=now,
            )
        )
        return "created", None

    def _create_position(self, context: _ImportContext, company_id: int, row: dict[str, str]) -> tuple[str, str | None]:
        code = self._normalize_code(row.get("code"))
        if context.position_repo.get_by_code(company_id, code) is not None:
            return "skipped", f"Position '{code}' already exists."
        now = datetime.utcnow()
        context.position_repo.save(
            Position(
                company_id=company_id,
                code=code,
                title=row.get("title", "").strip(),
                is_active=self._parse_bool_value(row.get("is_active"), True),
                created_at=now,
                updated_at=now,
            )
        )
        return "created", None

    def _create_employee(self, context: _ImportContext, company_id: int, row: dict[str, str]) -> tuple[str, str | None]:
        employee_number = self._normalize_code(row.get("employee_number"))
        if context.employee_repo.get_by_number(company_id, employee_number) is not None:
            return "skipped", f"Employee '{employee_number}' already exists."

        department = None
        department_code = self._normalize_code(row.get("department_code"))
        if department_code:
            department = context.department_repo.get_by_code(company_id, department_code)

        position = None
        position_code = self._normalize_code(row.get("position_code"))
        if position_code:
            position = context.position_repo.get_by_code(company_id, position_code)

        now = datetime.utcnow()
        first_name = row.get("first_name", "").strip()
        last_name = row.get("last_name", "").strip()
        context.employee_repo.save(
            Employee(
                company_id=company_id,
                employee_number=employee_number,
                first_name=first_name,
                last_name=last_name,
                display_name=f"{first_name} {last_name}".strip(),
                hire_date=self._parse_date_value(row.get("hire_date")) or date.today(),
                department_id=department.id if department else None,
                position_id=position.id if position else None,
                is_active=self._parse_bool_value(row.get("is_active"), True),
                created_at=now,
                updated_at=now,
            )
        )
        return "created", None

    def _create_component(self, context: _ImportContext, company_id: int, row: dict[str, str]) -> tuple[str, str | None]:
        component_code = self._normalize_code(row.get("component_code"))
        if context.component_repo.get_by_code(company_id, component_code) is not None:
            return "skipped", f"Component '{component_code}' already exists."

        expense_account = None
        expense_account_code = self._normalize_code(row.get("expense_account_code"))
        if expense_account_code:
            expense_account = context.account_repo.get_by_code(company_id, expense_account_code)

        liability_account = None
        liability_account_code = self._normalize_code(row.get("liability_account_code"))
        if liability_account_code:
            liability_account = context.account_repo.get_by_code(company_id, liability_account_code)

        now = datetime.utcnow()
        context.component_repo.save(
            PayrollComponent(
                company_id=company_id,
                component_code=component_code,
                component_name=row.get("component_name", "").strip(),
                component_type_code=row.get("component_type_code", "").strip(),
                calculation_method_code=row.get("calculation_method_code", "").strip(),
                is_taxable=self._parse_bool_value(row.get("is_taxable"), False),
                is_pensionable=self._parse_bool_value(row.get("is_pensionable"), False),
                expense_account_id=expense_account.id if expense_account else None,
                liability_account_id=liability_account.id if liability_account else None,
                is_active=self._parse_bool_value(row.get("is_active"), True),
                created_at=now,
                updated_at=now,
            )
        )
        return "created", None

    def _create_rule_set(self, context: _ImportContext, company_id: int, row: dict[str, str]) -> tuple[str, str | None]:
        rule_code = self._normalize_code(row.get("rule_code"))
        effective_from = self._parse_date_value(row.get("effective_from"))
        if effective_from and context.rule_set_repo.get_by_code_and_date(company_id, rule_code, effective_from) is not None:
            return "skipped", f"Rule set '{rule_code}' already exists for {effective_from}."

        now = datetime.utcnow()
        context.rule_set_repo.save(
            PayrollRuleSet(
                company_id=company_id,
                rule_code=rule_code,
                rule_name=row.get("rule_name", "").strip(),
                rule_type_code=row.get("rule_type_code", "").strip(),
                effective_from=effective_from or date.today(),
                effective_to=self._parse_date_value(row.get("effective_to")),
                calculation_basis_code=row.get("calculation_basis_code", "").strip(),
                is_active=self._parse_bool_value(row.get("is_active"), True),
                created_at=now,
                updated_at=now,
            )
        )
        return "created", None

    def _create_rule_bracket(self, context: _ImportContext, company_id: int, row: dict[str, str]) -> tuple[str, str | None]:
        rule_code = self._normalize_code(row.get("rule_code"))
        effective_from = self._parse_date_value(row.get("effective_from"))
        rule_set = context.rule_set_repo.get_by_code_and_date(company_id, rule_code, effective_from or date.today())
        if rule_set is None:
            return "error", f"Rule set '{rule_code}' was not found for the supplied effective date."

        line_number = int((row.get("line_number") or "0").strip())
        if context.rule_set_repo.get_bracket(rule_set.id, line_number) is not None:
            return "skipped", f"Bracket line {line_number} already exists for rule set '{rule_code}'."

        context.rule_set_repo.save_bracket(
            PayrollRuleBracket(
                payroll_rule_set_id=rule_set.id,
                line_number=line_number,
                lower_bound_amount=self._parse_decimal_value(row.get("lower_bound_amount")),
                upper_bound_amount=self._parse_decimal_value(row.get("upper_bound_amount")),
                rate_percent=self._parse_decimal_value(row.get("rate_percent")),
                fixed_amount=self._parse_decimal_value(row.get("fixed_amount")),
                deduction_amount=self._parse_decimal_value(row.get("deduction_amount")),
                cap_amount=self._parse_decimal_value(row.get("cap_amount")),
            )
        )
        return "created", None

    def _create_profile(self, context: _ImportContext, company_id: int, row: dict[str, str]) -> tuple[str, str | None]:
        employee_number = self._normalize_code(row.get("employee_number"))
        employee = context.employee_repo.get_by_number(company_id, employee_number)
        if employee is None:
            return "error", f"Employee '{employee_number}' was not found."

        effective_from = self._parse_date_value(row.get("effective_from"))
        if effective_from and context.profile_repo.check_duplicate(company_id, employee.id, effective_from):
            return "skipped", f"Compensation profile for employee '{employee_number}' already exists for {effective_from}."

        context.profile_repo.save(
            EmployeeCompensationProfile(
                company_id=company_id,
                employee_id=employee.id,
                profile_name=row.get("profile_name", "").strip(),
                basic_salary=self._parse_decimal_value(row.get("basic_salary")) or Decimal("0"),
                currency_code=self._normalize_code(row.get("currency_code")),
                effective_from=effective_from or date.today(),
                effective_to=self._parse_date_value(row.get("effective_to")),
                notes=(row.get("notes") or "").strip() or None,
                is_active=self._parse_bool_value(row.get("is_active"), True),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        return "created", None

    def _create_assignment(self, context: _ImportContext, company_id: int, row: dict[str, str]) -> tuple[str, str | None]:
        employee_number = self._normalize_code(row.get("employee_number"))
        employee = context.employee_repo.get_by_number(company_id, employee_number)
        if employee is None:
            return "error", f"Employee '{employee_number}' was not found."

        component_code = self._normalize_code(row.get("component_code"))
        component = context.component_repo.get_by_code(company_id, component_code)
        if component is None:
            return "error", f"Component '{component_code}' was not found."

        effective_from = self._parse_date_value(row.get("effective_from"))
        if effective_from and context.assignment_repo.check_duplicate(company_id, employee.id, component.id, effective_from):
            return "skipped", f"Assignment for employee '{employee_number}' and component '{component_code}' already exists for {effective_from}."

        context.assignment_repo.save(
            EmployeeComponentAssignment(
                company_id=company_id,
                employee_id=employee.id,
                component_id=component.id,
                override_amount=self._parse_decimal_value(row.get("override_amount")),
                override_rate=self._parse_decimal_value(row.get("override_rate")),
                effective_from=effective_from or date.today(),
                effective_to=self._parse_date_value(row.get("effective_to")),
                is_active=self._parse_bool_value(row.get("is_active"), True),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        return "created", None

    def _build_context(self, session: Session) -> _ImportContext:
        return _ImportContext(
            department_repo=self._dept_repo_factory(session),
            position_repo=self._pos_repo_factory(session),
            employee_repo=self._emp_repo_factory(session),
            component_repo=self._component_repo_factory(session),
            rule_set_repo=self._rule_set_repo_factory(session),
            profile_repo=self._profile_repo_factory(session),
            assignment_repo=self._assignment_repo_factory(session),
            account_repo=self._account_repo_factory(session),
            currency_repo=self._currency_repo_factory(session),
        )

    @staticmethod
    def _read_csv(file_path: str) -> list[dict[str, str]]:
        path = Path(file_path)
        if not path.exists():
            raise ValidationError(f"File not found: {file_path}")
        if path.suffix.lower() != ".csv":
            raise ValidationError("Only CSV files are supported.")

        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")

        reader = csv.DictReader(StringIO(text))
        return list(reader)

    @staticmethod
    def _validate_headers(expected: tuple[str, ...], found: tuple[str, ...]) -> None:
        missing = [column for column in expected if column not in found]
        if missing:
            raise ValidationError(f"CSV is missing required columns: {', '.join(missing)}")

    @staticmethod
    def _expected_columns(entity_type: str) -> tuple[str, ...]:
        column_map = {
            "departments": _DEPARTMENT_COLUMNS,
            "positions": _POSITION_COLUMNS,
            "employees": _EMPLOYEE_COLUMNS,
            "payroll_components": _COMPONENT_COLUMNS,
            "payroll_rule_sets": _RULE_SET_COLUMNS,
            "payroll_rule_brackets": _RULE_BRACKET_COLUMNS,
            "employee_compensation_profiles": _PROFILE_COLUMNS,
            "employee_component_assignments": _ASSIGNMENT_COLUMNS,
        }
        try:
            return column_map[entity_type]
        except KeyError as exc:
            raise ValidationError(f"Unsupported import type: '{entity_type}'.") from exc

    @staticmethod
    def _required_columns(entity_type: str) -> tuple[str, ...]:
        required_map = {
            "departments": ("code", "name"),
            "positions": ("code", "title"),
            "employees": ("employee_number", "first_name", "last_name", "hire_date"),
            "payroll_components": (
                "component_code",
                "component_name",
                "component_type_code",
                "calculation_method_code",
            ),
            "payroll_rule_sets": (
                "rule_code",
                "rule_name",
                "rule_type_code",
                "calculation_basis_code",
                "effective_from",
            ),
            "payroll_rule_brackets": ("rule_code", "effective_from", "line_number"),
            "employee_compensation_profiles": (
                "employee_number",
                "profile_name",
                "basic_salary",
                "currency_code",
                "effective_from",
            ),
            "employee_component_assignments": (
                "employee_number",
                "component_code",
                "effective_from",
            ),
        }
        try:
            return required_map[entity_type]
        except KeyError as exc:
            raise ValidationError(f"Unsupported import type: '{entity_type}'.") from exc

    @staticmethod
    def _required_text(
        row: dict[str, str],
        column: str,
        add_issue,
    ) -> str:
        value = (row.get(column) or "").strip()
        if not value:
            add_issue(column, f"{column.replace('_', ' ').title()} is required.")
        return value

    def _required_code(self, row: dict[str, str], column: str, add_issue) -> str:
        value = self._normalize_code(row.get(column))
        if not value:
            add_issue(column, f"{column.replace('_', ' ').title()} is required.")
        return value

    def _parse_required_date(self, row: dict[str, str], column: str, add_issue) -> date | None:
        value = (row.get(column) or "").strip()
        if not value:
            add_issue(column, f"{column.replace('_', ' ').title()} is required.")
            return None
        parsed = self._parse_date_value(value)
        if parsed is None:
            add_issue(column, f"Invalid date format: '{value}'.")
        return parsed

    def _parse_optional_date(self, row: dict[str, str], column: str, add_issue) -> date | None:
        value = (row.get(column) or "").strip()
        if not value:
            return None
        parsed = self._parse_date_value(value)
        if parsed is None:
            add_issue(column, f"Invalid date format: '{value}'.")
        return parsed

    def _parse_required_decimal(self, row: dict[str, str], column: str, add_issue) -> Decimal | None:
        value = (row.get(column) or "").strip()
        if not value:
            add_issue(column, f"{column.replace('_', ' ').title()} is required.")
            return None
        parsed = self._parse_decimal_value(value)
        if parsed is None:
            add_issue(column, f"Invalid decimal value: '{value}'.")
        return parsed

    def _parse_optional_decimal(self, row: dict[str, str], column: str, add_issue) -> Decimal | None:
        value = (row.get(column) or "").strip()
        if not value:
            return None
        parsed = self._parse_decimal_value(value)
        if parsed is None:
            add_issue(column, f"Invalid decimal value: '{value}'.")
        return parsed

    def _parse_required_int(self, row: dict[str, str], column: str, add_issue) -> int | None:
        value = (row.get(column) or "").strip()
        if not value:
            add_issue(column, f"{column.replace('_', ' ').title()} is required.")
            return None
        try:
            parsed = int(value)
        except ValueError:
            add_issue(column, f"Invalid integer value: '{value}'.")
            return None
        if parsed < 1:
            add_issue(column, f"{column.replace('_', ' ').title()} must be at least 1.")
        return parsed

    def _parse_bool(self, value: str | None, column: str, add_issue) -> bool | None:
        if value is None or not value.strip():
            return None
        try:
            return self._parse_bool_value(value, False)
        except ValidationError as exc:
            add_issue(column, str(exc))
            return None

    @staticmethod
    def _parse_bool_value(value: str | None, default: bool) -> bool:
        if value is None or not value.strip():
            return default
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        raise ValidationError(f"Invalid boolean value '{value}'.")

    @staticmethod
    def _parse_decimal_value(value: str | None) -> Decimal | None:
        if value is None or not value.strip():
            return None
        try:
            return Decimal(value.strip())
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _parse_date_value(value: str | None) -> date | None:
        if value is None or not value.strip():
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_code(value: str | None) -> str:
        return (value or "").strip().upper()
