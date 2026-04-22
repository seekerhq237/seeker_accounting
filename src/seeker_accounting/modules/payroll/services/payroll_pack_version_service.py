"""Pack version management — list versions, preview and execute rollovers.

A rollover applies a new pack version to a company. Existing components and
rule sets are never overwritten; only missing ones are created. The company's
statutory_pack_version_code is updated to the new pack code.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.dto.payroll_pack_version_dto import (
    PackRolloverPreviewDTO,
    PackRolloverResultDTO,
    PackVersionListItemDTO,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_PACK_APPLY
from seeker_accounting.modules.payroll.repositories.company_payroll_setting_repository import (
    CompanyPayrollSettingRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import (
    PayrollRuleSetRepository,
)
from seeker_accounting.modules.payroll.statutory_packs.pack_registry import (
    PackVersionDescriptor,
    get_all_packs,
    get_pack_by_code,
)
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CompanyPayrollSettingRepositoryFactory = Callable[[Session], CompanyPayrollSettingRepository]
PayrollComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]
PayrollRuleSetRepositoryFactory = Callable[[Session], PayrollRuleSetRepository]


class PayrollPackVersionService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        settings_repository_factory: CompanyPayrollSettingRepositoryFactory,
        component_repository_factory: PayrollComponentRepositoryFactory,
        rule_set_repository_factory: PayrollRuleSetRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._company_repo_factory = company_repository_factory
        self._settings_repo_factory = settings_repository_factory
        self._component_repo_factory = component_repository_factory
        self._rule_set_repo_factory = rule_set_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    def list_available_versions(self, company_id: int) -> list[PackVersionListItemDTO]:
        """List all available pack versions, marking which one is current."""
        current_code = self._get_current_pack_code(company_id)
        return [
            PackVersionListItemDTO(
                pack_code=p.pack_code,
                display_name=p.display_name,
                country_code=p.country_code,
                effective_from=p.effective_from,
                description=p.description,
                is_current=(p.pack_code == current_code),
            )
            for p in get_all_packs()
        ]

    def preview_rollover(
        self, company_id: int, target_pack_code: str
    ) -> PackRolloverPreviewDTO:
        """Preview what a rollover to the target pack would create."""
        self._permission_service.require_permission(PAYROLL_PACK_APPLY)
        target = self._resolve_pack(target_pack_code)
        current_code = self._get_current_pack_code(company_id)

        comp_seeds = target.pack_module.COMPONENT_SEEDS
        rule_seeds = target.pack_module.RULE_SET_SEEDS
        effective_from = target.pack_module.PACK_EFFECTIVE_FROM

        with self._uow_factory() as uow:
            comp_repo = self._component_repo_factory(uow.session)
            rule_repo = self._rule_set_repo_factory(uow.session)

            existing_comps = 0
            new_comps = 0
            for code, *_ in comp_seeds:
                if comp_repo.get_by_code(company_id, code) is not None:
                    existing_comps += 1
                else:
                    new_comps += 1

            existing_rules = 0
            new_rules = 0
            for code, *_rest in rule_seeds:
                if rule_repo.get_by_code_and_date(company_id, code, effective_from) is not None:
                    existing_rules += 1
                else:
                    new_rules += 1

        if new_comps == 0 and new_rules == 0:
            msg = "All components and rule sets from this pack already exist. No changes needed."
        else:
            parts = []
            if new_comps > 0:
                parts.append(f"{new_comps} new component(s)")
            if new_rules > 0:
                parts.append(f"{new_rules} new rule set(s)")
            msg = f"Rollover will create {' and '.join(parts)}. Existing records will not be modified."

        return PackRolloverPreviewDTO(
            current_pack_code=current_code,
            target_pack_code=target_pack_code,
            target_display_name=target.display_name,
            components_to_create=new_comps,
            rule_sets_to_create=new_rules,
            existing_components=existing_comps,
            existing_rule_sets=existing_rules,
            message=msg,
        )

    def execute_rollover(
        self, company_id: int, target_pack_code: str
    ) -> PackRolloverResultDTO:
        """Apply a target pack version. Delegates to PayrollStatutoryPackService.apply_pack logic."""
        self._permission_service.require_permission(PAYROLL_PACK_APPLY)
        target = self._resolve_pack(target_pack_code)
        current_code = self._get_current_pack_code(company_id)

        from datetime import datetime
        import json
        from seeker_accounting.modules.payroll.models.company_payroll_setting import (
            CompanyPayrollSetting,
        )
        from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
        from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
        from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet

        pack_mod = target.pack_module
        comp_seeds = pack_mod.COMPONENT_SEEDS
        rule_seeds = pack_mod.RULE_SET_SEEDS
        effective_from = pack_mod.PACK_EFFECTIVE_FROM

        with self._uow_factory() as uow:
            company = self._company_repo_factory(uow.session).get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company {company_id} not found.")

            comp_repo = self._component_repo_factory(uow.session)
            rule_repo = self._rule_set_repo_factory(uow.session)
            settings_repo = self._settings_repo_factory(uow.session)
            now = datetime.utcnow()

            comps_created = comps_skipped = 0
            rules_created = rules_skipped = 0
            brackets_created = 0

            for code, name, type_code, method_code, is_taxable, is_pensionable, _vr in comp_seeds:
                if comp_repo.get_by_code(company_id, code) is not None:
                    comps_skipped += 1
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
                comps_created += 1

            for code, name, type_code, basis_code, bracket_defs, _vr in rule_seeds:
                if rule_repo.get_by_code_and_date(company_id, code, effective_from) is not None:
                    rules_skipped += 1
                    continue
                rule_set = PayrollRuleSet(
                    company_id=company_id,
                    rule_code=code,
                    rule_name=name,
                    rule_type_code=type_code,
                    effective_from=effective_from,
                    effective_to=None,
                    calculation_basis_code=basis_code,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                rule_repo.save(rule_set)
                rules_created += 1

                for line_no, lower, upper, rate, fixed, deduction, cap in bracket_defs:
                    bracket = PayrollRuleBracket(
                        payroll_rule_set_id=None,
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

            # Update settings
            settings = settings_repo.get_by_company(company_id)
            previous_pack_code = settings.statutory_pack_version_code if settings is not None else None
            if settings is not None:
                if settings.statutory_pack_version_code != target_pack_code:
                    settings.statutory_pack_version_code = target_pack_code
                    settings.updated_at = now
                    settings_repo.save(settings)
                    settings_action = "updated"
                else:
                    settings_action = "untouched"
            else:
                settings = CompanyPayrollSetting(
                    company_id=company_id,
                    statutory_pack_version_code=target_pack_code,
                    default_pay_frequency_code="monthly",
                    default_payroll_currency_code=company.base_currency_code,
                    updated_at=now,
                )
                settings_repo.save(settings)
                settings_action = "created"

            superseded_previous_pack_code = (
                previous_pack_code
                if previous_pack_code and previous_pack_code != target_pack_code
                else None
            )
            outcome_code = (
                "superseded"
                if superseded_previous_pack_code is not None
                else settings_action
            )

            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_PACK_ROLLED_OVER",
                    module_code="payroll",
                    entity_type="statutory_pack",
                    entity_id=None,
                    description=(
                        f"Rolled payroll statutory pack to '{target_pack_code}'."
                    ),
                    detail_json=json.dumps(
                        {
                            "previous_pack_code": previous_pack_code,
                            "new_pack_code": target_pack_code,
                            "components_created": comps_created,
                            "components_skipped": comps_skipped,
                            "rule_sets_created": rules_created,
                            "rule_sets_skipped": rules_skipped,
                            "brackets_created": brackets_created,
                            "settings_action": settings_action,
                            "outcome_code": outcome_code,
                        }
                    ),
                ),
            )

            uow.commit()

        msg_parts = [f"Pack '{target_pack_code}' applied."]
        if comps_created:
            msg_parts.append(f"Components: {comps_created} created, {comps_skipped} already present.")
        elif comps_skipped:
            msg_parts.append(f"Components: {comps_skipped} untouched existing.")
        if rules_created:
            msg_parts.append(f"Rule sets: {rules_created} created, {rules_skipped} already present.")
        elif rules_skipped:
            msg_parts.append(f"Rule sets: {rules_skipped} untouched existing.")
        if brackets_created:
            msg_parts.append(f"Brackets: {brackets_created} created.")
        msg_parts.append(f"Settings: {settings_action}.")
        if superseded_previous_pack_code:
            msg_parts.append(f"Superseded previous pack '{superseded_previous_pack_code}'.")
        if settings_action == "untouched" and comps_created == 0 and rules_created == 0 and brackets_created == 0:
            msg_parts.append("No payroll setup rows needed changes.")

        return PackRolloverResultDTO(
            previous_pack_code=current_code,
            new_pack_code=target_pack_code,
            components_created=comps_created,
            components_skipped=comps_skipped,
            rule_sets_created=rules_created,
            rule_sets_skipped=rules_skipped,
            brackets_created=brackets_created,
            settings_action=settings_action,
            superseded_previous_pack_code=superseded_previous_pack_code,
            outcome_code=outcome_code,
            message=" ".join(msg_parts),
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_current_pack_code(self, company_id: int) -> str | None:
        with self._uow_factory() as uow:
            settings_repo = self._settings_repo_factory(uow.session)
            settings = settings_repo.get_by_company(company_id)
            return settings.statutory_pack_version_code if settings else None

    @staticmethod
    def _resolve_pack(pack_code: str) -> PackVersionDescriptor:
        pack = get_pack_by_code(pack_code)
        if pack is None:
            raise ValidationError(f"Statutory pack '{pack_code}' is not available.")
        return pack
