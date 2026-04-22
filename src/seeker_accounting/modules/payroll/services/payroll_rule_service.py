from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.dto.payroll_rule_dto import (
    CreatePayrollRuleSetCommand,
    DeletePayrollRuleBracketCommand,
    PayrollRuleBracketDTO,
    PayrollRuleSetDetailDTO,
    PayrollRuleSetListItemDTO,
    UpdatePayrollRuleSetCommand,
    UpsertPayrollRuleBracketCommand,
)
from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import (
    PayrollRuleSetRepository,
)
from seeker_accounting.platform.exceptions import ConflictError, NotFoundError, ValidationError

PayrollRuleSetRepositoryFactory = Callable[[Session], PayrollRuleSetRepository]
CompanyRepositoryFactory = Callable[[Session], CompanyRepository]

_VALID_RULE_TYPES = frozenset({
    "pit", "pension_employee", "pension_employer", "accident_risk",
    "overtime", "levy", "other",
})

_VALID_CALCULATION_BASES = frozenset({
    "gross_salary", "basic_salary", "taxable_gross", "pensionable_gross",
    "fixed", "other",
})


class PayrollRuleService:
    """Manage payroll rule sets and their bracket lines."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        rule_set_repository_factory: PayrollRuleSetRepositoryFactory,
        company_repository_factory: CompanyRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._rule_set_repository_factory = rule_set_repository_factory
        self._company_repository_factory = company_repository_factory

    # ── Rule Set Queries ──────────────────────────────────────────────────────

    def list_rule_sets(
        self,
        company_id: int,
        active_only: bool = False,
        rule_type_code: str | None = None,
    ) -> list[PayrollRuleSetListItemDTO]:
        with self._unit_of_work_factory() as uow:
            rows = self._rule_set_repository_factory(uow.session).list_by_company(
                company_id, active_only=active_only, rule_type_code=rule_type_code
            )
            return [self._to_list_dto(r) for r in rows]

    def get_rule_set(self, company_id: int, rule_set_id: int) -> PayrollRuleSetDetailDTO:
        with self._unit_of_work_factory() as uow:
            row = self._rule_set_repository_factory(uow.session).get_by_id(
                company_id, rule_set_id
            )
            if row is None:
                raise NotFoundError(f"Payroll rule set {rule_set_id} not found.")
            return self._to_detail_dto(row)

    # ── Rule Set Commands ─────────────────────────────────────────────────────

    def create_rule_set(
        self, company_id: int, command: CreatePayrollRuleSetCommand
    ) -> PayrollRuleSetDetailDTO:
        with self._unit_of_work_factory() as uow:
            self._require_company(uow.session, company_id)
            self._validate_rule_set_fields(
                command.rule_code, command.rule_name,
                command.rule_type_code, command.calculation_basis_code,
                command.effective_from, command.effective_to,
            )
            repo = self._rule_set_repository_factory(uow.session)
            if repo.get_by_code_and_date(
                company_id, command.rule_code.strip().upper(), command.effective_from
            ) is not None:
                raise ConflictError(
                    f"Rule set '{command.rule_code}' with effective date "
                    f"{command.effective_from} already exists."
                )
            now = datetime.utcnow()
            rule_set = PayrollRuleSet(
                company_id=company_id,
                rule_code=command.rule_code.strip().upper(),
                rule_name=command.rule_name.strip(),
                rule_type_code=command.rule_type_code,
                effective_from=command.effective_from,
                effective_to=command.effective_to,
                calculation_basis_code=command.calculation_basis_code,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            repo.save(rule_set)
            uow.commit()
            row = self._rule_set_repository_factory(uow.session).get_by_id(
                company_id, rule_set.id
            )
            return self._to_detail_dto(row)  # type: ignore[arg-type]

    def update_rule_set(
        self, company_id: int, rule_set_id: int, command: UpdatePayrollRuleSetCommand
    ) -> PayrollRuleSetDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._rule_set_repository_factory(uow.session)
            rule_set = repo.get_by_id(company_id, rule_set_id)
            if rule_set is None:
                raise NotFoundError(f"Payroll rule set {rule_set_id} not found.")
            self._validate_rule_set_fields(
                command.rule_code, command.rule_name,
                command.rule_type_code, command.calculation_basis_code,
                command.effective_from, command.effective_to,
            )
            existing = repo.get_by_code_and_date(
                company_id, command.rule_code.strip().upper(), command.effective_from
            )
            if existing is not None and existing.id != rule_set_id:
                raise ConflictError(
                    f"Rule set '{command.rule_code}' with effective date "
                    f"{command.effective_from} already exists."
                )
            rule_set.rule_code = command.rule_code.strip().upper()
            rule_set.rule_name = command.rule_name.strip()
            rule_set.rule_type_code = command.rule_type_code
            rule_set.effective_from = command.effective_from
            rule_set.effective_to = command.effective_to
            rule_set.calculation_basis_code = command.calculation_basis_code
            rule_set.is_active = command.is_active
            rule_set.updated_at = datetime.utcnow()
            repo.save(rule_set)
            uow.commit()
            row = self._rule_set_repository_factory(uow.session).get_by_id(
                company_id, rule_set_id
            )
            return self._to_detail_dto(row)  # type: ignore[arg-type]

    # ── Bracket Commands ──────────────────────────────────────────────────────

    def upsert_bracket(
        self,
        company_id: int,
        rule_set_id: int,
        command: UpsertPayrollRuleBracketCommand,
    ) -> PayrollRuleSetDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._rule_set_repository_factory(uow.session)
            rule_set = repo.get_by_id(company_id, rule_set_id)
            if rule_set is None:
                raise NotFoundError(f"Payroll rule set {rule_set_id} not found.")
            self._validate_bracket(command)
            bracket = repo.get_bracket(rule_set_id, command.line_number)
            if bracket is None:
                bracket = PayrollRuleBracket(
                    payroll_rule_set_id=rule_set_id,
                    line_number=command.line_number,
                )
            bracket.lower_bound_amount = command.lower_bound_amount
            bracket.upper_bound_amount = command.upper_bound_amount
            bracket.rate_percent = command.rate_percent
            bracket.fixed_amount = command.fixed_amount
            bracket.deduction_amount = command.deduction_amount
            bracket.cap_amount = command.cap_amount
            repo.save_bracket(bracket)
            uow.commit()
            row = self._rule_set_repository_factory(uow.session).get_by_id(
                company_id, rule_set_id
            )
            return self._to_detail_dto(row)  # type: ignore[arg-type]

    def delete_bracket(
        self,
        company_id: int,
        rule_set_id: int,
        command: DeletePayrollRuleBracketCommand,
    ) -> PayrollRuleSetDetailDTO:
        with self._unit_of_work_factory() as uow:
            repo = self._rule_set_repository_factory(uow.session)
            rule_set = repo.get_by_id(company_id, rule_set_id)
            if rule_set is None:
                raise NotFoundError(f"Payroll rule set {rule_set_id} not found.")
            bracket = repo.get_bracket(rule_set_id, command.line_number)
            if bracket is None:
                raise NotFoundError(
                    f"Bracket line {command.line_number} not found in rule set {rule_set_id}."
                )
            repo.delete_bracket(bracket)
            uow.commit()
            row = self._rule_set_repository_factory(uow.session).get_by_id(
                company_id, rule_set_id
            )
            return self._to_detail_dto(row)  # type: ignore[arg-type]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require_company(self, session: Session, company_id: int) -> None:
        if self._company_repository_factory(session).get_by_id(company_id) is None:
            raise NotFoundError(f"Company {company_id} not found.")

    def _validate_rule_set_fields(
        self,
        rule_code: str,
        rule_name: str,
        rule_type_code: str,
        calculation_basis_code: str,
        effective_from: object,
        effective_to: object,
    ) -> None:
        if not rule_code or not rule_code.strip():
            raise ValidationError("Rule code is required.")
        if not rule_name or not rule_name.strip():
            raise ValidationError("Rule name is required.")
        if rule_type_code not in _VALID_RULE_TYPES:
            raise ValidationError(
                f"Rule type '{rule_type_code}' is not valid. "
                f"Valid: {', '.join(sorted(_VALID_RULE_TYPES))}."
            )
        if calculation_basis_code not in _VALID_CALCULATION_BASES:
            raise ValidationError(
                f"Calculation basis '{calculation_basis_code}' is not valid. "
                f"Valid: {', '.join(sorted(_VALID_CALCULATION_BASES))}."
            )
        if effective_from is not None and effective_to is not None:
            if effective_to < effective_from:  # type: ignore[operator]
                raise ValidationError("Effective to date cannot be before effective from date.")

    def _validate_bracket(self, cmd: UpsertPayrollRuleBracketCommand) -> None:
        if cmd.line_number < 1:
            raise ValidationError("Bracket line number must be at least 1.")
        if (cmd.lower_bound_amount is not None
                and cmd.upper_bound_amount is not None
                and cmd.upper_bound_amount <= cmd.lower_bound_amount):
            raise ValidationError(
                "Bracket upper bound must be greater than lower bound."
            )

    def _to_list_dto(self, rule_set: PayrollRuleSet) -> PayrollRuleSetListItemDTO:
        return PayrollRuleSetListItemDTO(
            id=rule_set.id,
            company_id=rule_set.company_id,
            rule_code=rule_set.rule_code,
            rule_name=rule_set.rule_name,
            rule_type_code=rule_set.rule_type_code,
            effective_from=rule_set.effective_from,
            effective_to=rule_set.effective_to,
            calculation_basis_code=rule_set.calculation_basis_code,
            is_active=rule_set.is_active,
            bracket_count=len(rule_set.brackets),
        )

    def _to_detail_dto(self, rule_set: PayrollRuleSet) -> PayrollRuleSetDetailDTO:
        return PayrollRuleSetDetailDTO(
            id=rule_set.id,
            company_id=rule_set.company_id,
            rule_code=rule_set.rule_code,
            rule_name=rule_set.rule_name,
            rule_type_code=rule_set.rule_type_code,
            effective_from=rule_set.effective_from,
            effective_to=rule_set.effective_to,
            calculation_basis_code=rule_set.calculation_basis_code,
            is_active=rule_set.is_active,
            created_at=rule_set.created_at,
            updated_at=rule_set.updated_at,
            brackets=tuple(self._bracket_to_dto(b) for b in rule_set.brackets),
        )

    def _bracket_to_dto(self, bracket: PayrollRuleBracket) -> PayrollRuleBracketDTO:
        return PayrollRuleBracketDTO(
            id=bracket.id,
            payroll_rule_set_id=bracket.payroll_rule_set_id,
            line_number=bracket.line_number,
            lower_bound_amount=bracket.lower_bound_amount,
            upper_bound_amount=bracket.upper_bound_amount,
            rate_percent=bracket.rate_percent,
            fixed_amount=bracket.fixed_amount,
            deduction_amount=bracket.deduction_amount,
            cap_amount=bracket.cap_amount,
        )
