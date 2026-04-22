from __future__ import annotations

"""Cameroon statutory payroll pack seed service.

Creates the default payroll component definitions and effective-dated rule set
scaffolding for Cameroon 2024 compliance.  Seeding is deterministic and
safe to re-run: records that already exist (matched by code / code+date) are
skipped; no existing row is overwritten.

Pack data is defined in:
  seeker_accounting.modules.payroll.statutory_packs.cameroon_default_pack

This service is kept for backward compatibility.  New code should prefer
PayrollStatutoryPackService.apply_pack() which also updates settings.
"""

from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.dto.payroll_setup_dto import PayrollSeedResultDTO
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import (
    PayrollRuleSetRepository,
)
from seeker_accounting.modules.payroll.statutory_packs import cameroon_default_pack as _cmr
from seeker_accounting.platform.exceptions import NotFoundError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
PayrollComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]
PayrollRuleSetRepositoryFactory = Callable[[Session], PayrollRuleSetRepository]

# ── Re-export constants from pack module for backward compat ──────────────────
_VERSION_CODE = _cmr.PACK_CODE
_EFFECTIVE_FROM = _cmr.PACK_EFFECTIVE_FROM
_COMPONENT_SEEDS = _cmr.COMPONENT_SEEDS
_RULE_SET_SEEDS = _cmr.RULE_SET_SEEDS


class CameroonPayrollSeedService:
    """Seed a Cameroon 2024 statutory payroll pack for a company.

    Idempotent: records already present (by code or code+date) are skipped.
    No existing active or inactive records are overwritten.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        component_repository_factory: PayrollComponentRepositoryFactory,
        rule_set_repository_factory: PayrollRuleSetRepositoryFactory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._component_repository_factory = component_repository_factory
        self._rule_set_repository_factory = rule_set_repository_factory

    def seed(self, company_id: int) -> PayrollSeedResultDTO:
        """Seed the Cameroon 2024 statutory pack for the given company.

        Returns a result DTO describing how many records were created vs skipped.
        """
        with self._unit_of_work_factory() as uow:
            if self._company_repository_factory(uow.session).get_by_id(company_id) is None:
                raise NotFoundError(f"Company {company_id} not found.")

            comp_repo = self._component_repository_factory(uow.session)
            rule_repo = self._rule_set_repository_factory(uow.session)
            now = datetime.utcnow()

            components_created = 0
            components_skipped = 0
            rule_sets_created = 0
            rule_sets_skipped = 0
            brackets_created = 0

            # ── Components ────────────────────────────────────────────────────
            for code, name, type_code, method_code, is_taxable, is_pensionable, _vr in _COMPONENT_SEEDS:
                existing = comp_repo.get_by_code(company_id, code)
                if existing is not None:
                    components_skipped += 1
                    continue
                comp = PayrollComponent(
                    company_id=company_id,
                    component_code=code,
                    component_name=name,
                    component_type_code=type_code,
                    calculation_method_code=method_code,
                    is_taxable=is_taxable,
                    is_pensionable=is_pensionable,
                    expense_account_id=None,
                    liability_account_id=None,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                comp_repo.save(comp)
                components_created += 1

            # ── Rule sets + brackets ──────────────────────────────────────────
            for code, name, type_code, basis_code, bracket_defs, _vr in _RULE_SET_SEEDS:
                existing = rule_repo.get_by_code_and_date(company_id, code, _EFFECTIVE_FROM)
                if existing is not None:
                    rule_sets_skipped += 1
                    continue
                rule_set = PayrollRuleSet(
                    company_id=company_id,
                    rule_code=code,
                    rule_name=name,
                    rule_type_code=type_code,
                    effective_from=_EFFECTIVE_FROM,
                    effective_to=None,
                    calculation_basis_code=basis_code,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                rule_repo.save(rule_set)
                rule_sets_created += 1

                for line_no, lower, upper, rate, fixed, deduction, cap in bracket_defs:
                    bracket = PayrollRuleBracket(
                        payroll_rule_set_id=None,  # set after flush
                        line_number=line_no,
                        lower_bound_amount=lower,
                        upper_bound_amount=upper,
                        rate_percent=rate,
                        fixed_amount=fixed,
                        deduction_amount=deduction,
                        cap_amount=cap,
                    )
                    rule_set.brackets.append(bracket)
                    brackets_created += 1

            uow.commit()

        msg_parts = [
            f"Cameroon {_VERSION_CODE} seed complete.",
            f"Components: {components_created} created, {components_skipped} already present.",
            f"Rule sets: {rule_sets_created} created, {rule_sets_skipped} already present.",
            f"Brackets: {brackets_created} created.",
        ]
        if components_skipped + rule_sets_skipped > 0:
            msg_parts.append(
                "Existing records were not modified. "
                "Use the rule set editor to adjust rates or add new effective-dated versions."
            )

        return PayrollSeedResultDTO(
            version_code=_VERSION_CODE,
            components_created=components_created,
            components_skipped=components_skipped,
            rule_sets_created=rule_sets_created,
            rule_sets_skipped=rule_sets_skipped,
            brackets_created=brackets_created,
            message=" ".join(msg_parts),
        )
