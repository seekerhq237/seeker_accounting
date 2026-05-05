from __future__ import annotations

"""Statutory payroll pack application service.

Responsibilities:
- Expose the list of available statutory packs (currently Cameroon 2024 only).
- Apply a pack to a company idempotently:
    * create missing payroll components
    * create missing rule sets with brackets
    * update company_payroll_settings.statutory_pack_version_code
    * never overwrite existing records
- Return a structured result with created / skipped counts.
"""

import json
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.companies.repositories.company_repository import CompanyRepository
from seeker_accounting.modules.payroll.dto.payroll_statutory_pack_dto import (
    ApplyPackResultDTO,
    StatutoryPackSummaryDTO,
)
from seeker_accounting.modules.payroll.payroll_permissions import PAYROLL_PACK_APPLY
from seeker_accounting.modules.payroll.models.company_payroll_setting import CompanyPayrollSetting
from seeker_accounting.modules.payroll.models.payroll_authority import PayrollAuthority
from seeker_accounting.modules.payroll.models.payroll_component import PayrollComponent
from seeker_accounting.modules.payroll.models.payroll_component_authority_map import (
    PayrollComponentAuthorityMap,
)
from seeker_accounting.modules.payroll.models.payroll_rule_bracket import PayrollRuleBracket
from seeker_accounting.modules.payroll.models.payroll_rule_set import PayrollRuleSet
from seeker_accounting.modules.payroll.repositories.company_payroll_setting_repository import (
    CompanyPayrollSettingRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_authority_repository import (
    PayrollAuthorityRepository,
    PayrollComponentAuthorityMapRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_rule_set_repository import (
    PayrollRuleSetRepository,
)
from seeker_accounting.modules.payroll.statutory_packs import cameroon_default_pack as _cmr
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError

CompanyRepositoryFactory = Callable[[Session], CompanyRepository]
CompanyPayrollSettingRepositoryFactory = Callable[[Session], CompanyPayrollSettingRepository]
PayrollComponentRepositoryFactory = Callable[[Session], PayrollComponentRepository]
PayrollRuleSetRepositoryFactory = Callable[[Session], PayrollRuleSetRepository]
PayrollAuthorityRepositoryFactory = Callable[[Session], PayrollAuthorityRepository]
PayrollComponentAuthorityMapRepositoryFactory = Callable[
    [Session], PayrollComponentAuthorityMapRepository
]

# ── Available packs registry ──────────────────────────────────────────────────
# Each entry maps pack_code → (pack_module, summary)
# Add new packs here as they are implemented.

_AVAILABLE_PACKS: dict[str, StatutoryPackSummaryDTO] = {
    _cmr.PACK_CODE: StatutoryPackSummaryDTO(
        pack_code=_cmr.PACK_CODE,
        display_name=_cmr.PACK_DISPLAY_NAME,
        country_code=_cmr.PACK_COUNTRY_CODE,
        description=_cmr.PACK_DESCRIPTION,
    ),
}


class PayrollStatutoryPackService:
    """Apply statutory payroll packs to companies.

    Idempotent: existing records are never overwritten; duplicate application
    is safe and returns counts of what was created vs already present.
    """

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        company_repository_factory: CompanyRepositoryFactory,
        settings_repository_factory: CompanyPayrollSettingRepositoryFactory,
        component_repository_factory: PayrollComponentRepositoryFactory,
        rule_set_repository_factory: PayrollRuleSetRepositoryFactory,
        permission_service: PermissionService,
        audit_service: AuditService,
        authority_repository_factory: PayrollAuthorityRepositoryFactory | None = None,
        component_authority_map_repository_factory: (
            PayrollComponentAuthorityMapRepositoryFactory | None
        ) = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._company_repository_factory = company_repository_factory
        self._settings_repository_factory = settings_repository_factory
        self._component_repository_factory = component_repository_factory
        self._rule_set_repository_factory = rule_set_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service
        self._authority_repository_factory = (
            authority_repository_factory or PayrollAuthorityRepository
        )
        self._component_authority_map_repository_factory = (
            component_authority_map_repository_factory
            or PayrollComponentAuthorityMapRepository
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def list_available_packs(self) -> list[StatutoryPackSummaryDTO]:
        """Return the list of packs that can be applied via apply_pack()."""
        return list(_AVAILABLE_PACKS.values())

    def apply_pack(self, company_id: int, pack_code: str) -> ApplyPackResultDTO:
        """Apply a statutory pack to the given company.

        Creates missing components and rule sets.  Never overwrites existing.
        Updates company_payroll_settings.statutory_pack_version_code on success.
        """
        if pack_code not in _AVAILABLE_PACKS:
            raise ValidationError(
                f"Statutory pack '{pack_code}' is not available. "
                f"Available: {', '.join(_AVAILABLE_PACKS)}."
            )

        self._permission_service.require_permission(PAYROLL_PACK_APPLY)

        with self._unit_of_work_factory() as uow:
            company = self._company_repository_factory(uow.session).get_by_id(company_id)
            if company is None:
                raise NotFoundError(f"Company {company_id} not found.")

            comp_repo = self._component_repository_factory(uow.session)
            rule_repo = self._rule_set_repository_factory(uow.session)
            settings_repo = self._settings_repository_factory(uow.session)
            now = datetime.utcnow()

            components_created = 0
            components_skipped = 0
            rule_sets_created = 0
            rule_sets_skipped = 0
            brackets_created = 0
            authorities_created = 0
            authorities_skipped = 0
            mappings_created = 0
            mappings_skipped = 0

            # ── Dispatch to pack data ─────────────────────────────────────────
            if pack_code == _cmr.PACK_CODE:
                component_seeds = _cmr.COMPONENT_SEEDS
                rule_set_seeds = _cmr.RULE_SET_SEEDS
                authority_seeds = _cmr.AUTHORITY_SEEDS
                mapping_seeds = _cmr.COMPONENT_AUTHORITY_MAP_SEEDS
                effective_from = _cmr.PACK_EFFECTIVE_FROM
                version_code = _cmr.PACK_CODE
            else:
                # Unreachable while _AVAILABLE_PACKS only lists Cameroon,
                # but guards against future incomplete wiring.
                raise ValidationError(f"No data handler for pack '{pack_code}'.")

            # ── Components ────────────────────────────────────────────────────
            for code, name, type_code, method_code, is_taxable, is_pensionable, _vr in component_seeds:
                if comp_repo.get_by_code(company_id, code) is not None:
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
            for code, name, type_code, basis_code, bracket_defs, _vr in rule_set_seeds:
                if rule_repo.get_by_code_and_date(company_id, code, effective_from) is not None:
                    rule_sets_skipped += 1
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
                rule_sets_created += 1

                for line_no, lower, upper, rate, fixed, deduction, cap in bracket_defs:
                    bracket = PayrollRuleBracket(
                        payroll_rule_set_id=None,  # resolved via cascade after flush
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

            # ── Authorities ───────────────────────────────────────────────────
            authority_repo = self._authority_repository_factory(uow.session)
            map_repo = self._component_authority_map_repository_factory(uow.session)
            authorities_by_code: dict[str, PayrollAuthority] = {}
            for (
                auth_code,
                auth_name,
                jurisdiction,
                cadence,
                deadline_day,
                deadline_rule,
                notes,
            ) in authority_seeds:
                existing = authority_repo.get_by_code(company_id, auth_code)
                if existing is not None:
                    authorities_by_code[auth_code] = existing
                    authorities_skipped += 1
                    continue
                authority = PayrollAuthority(
                    company_id=company_id,
                    code=auth_code,
                    name=auth_name,
                    jurisdiction_code=jurisdiction,
                    filing_cadence_code=cadence,
                    deadline_rule_code=deadline_rule,
                    deadline_day=deadline_day,
                    gl_liability_account_id=None,
                    notes=notes,
                    is_active=True,
                )
                authority_repo.save(authority)
                authorities_by_code[auth_code] = authority
                authorities_created += 1
            uow.session.flush()

            # ── Component → authority mappings ────────────────────────────────
            from decimal import Decimal as _Dec

            for (
                comp_code,
                auth_code,
                side,
                line_kind,
                fraction_str,
            ) in mapping_seeds:
                component = comp_repo.get_by_code(company_id, comp_code)
                if component is None:
                    # Component not in this pack (or filtered out); skip silently.
                    continue
                authority = authorities_by_code.get(auth_code)
                if authority is None:
                    # Authority not declared in this pack manifest; skip silently.
                    continue
                existing_map = map_repo.find(
                    company_id,
                    component_id=component.id,
                    authority_id=authority.id,
                    side=side,
                )
                if existing_map is not None:
                    mappings_skipped += 1
                    continue
                mapping = PayrollComponentAuthorityMap(
                    company_id=company_id,
                    component_id=component.id,
                    authority_id=authority.id,
                    side=side,
                    line_kind=line_kind,
                    fraction=_Dec(fraction_str),
                )
                map_repo.save(mapping)
                mappings_created += 1

            # ── Update statutory_pack_version_code in settings ────────────────
            settings_row = settings_repo.get_by_company(company_id)
            previous_pack_code = (
                settings_row.statutory_pack_version_code if settings_row is not None else None
            )
            if settings_row is not None:
                if settings_row.statutory_pack_version_code != version_code:
                    settings_row.statutory_pack_version_code = version_code
                    settings_row.updated_at = now
                    settings_repo.save(settings_row)
                    settings_action = "updated"
                else:
                    settings_action = "untouched"
            else:
                settings_row = CompanyPayrollSetting(
                    company_id=company_id,
                    statutory_pack_version_code=version_code,
                    default_pay_frequency_code="monthly",
                    default_payroll_currency_code=company.base_currency_code,
                    updated_at=now,
                )
                settings_repo.save(settings_row)
                settings_action = "created"

            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_PACK_APPLIED",
                    module_code="payroll",
                    entity_type="statutory_pack",
                    entity_id=None,
                    description=(
                        f"Applied statutory pack '{pack_code}' to company {company_id}."
                    ),
                    detail_json=json.dumps(
                        {
                            "pack_code": pack_code,
                            "components_created": components_created,
                            "components_skipped": components_skipped,
                            "rule_sets_created": rule_sets_created,
                            "rule_sets_skipped": rule_sets_skipped,
                            "brackets_created": brackets_created,
                            "authorities_created": authorities_created,
                            "authorities_skipped": authorities_skipped,
                            "mappings_created": mappings_created,
                            "mappings_skipped": mappings_skipped,
                            "settings_action": settings_action,
                            "previous_pack_code": previous_pack_code,
                            "new_pack_code": version_code,
                        }
                    ),
                ),
            )

            uow.commit()

        settings_updated = settings_action != "untouched"
        superseded_previous_pack_code = (
            previous_pack_code
            if previous_pack_code and previous_pack_code != version_code
            else None
        )
        msg_parts = [
            f"Pack '{pack_code}' applied.",
            f"Components: {components_created} created, {components_skipped} already present.",
            f"Rule sets: {rule_sets_created} created, {rule_sets_skipped} already present.",
            f"Brackets: {brackets_created} created.",
            f"Authorities: {authorities_created} created, {authorities_skipped} already present.",
            f"Mappings: {mappings_created} created, {mappings_skipped} already present.",
        ]
        msg_parts.append(f"Settings: {settings_action}.")
        if superseded_previous_pack_code:
            msg_parts.append(f"Superseded previous pack '{superseded_previous_pack_code}'.")
        if components_skipped + rule_sets_skipped > 0:
            msg_parts.append(
                "Existing records were left untouched. "
                "Use the rule set editor to adjust rates or add new effective-dated versions."
            )

        return ApplyPackResultDTO(
            pack_code=pack_code,
            version_code=version_code,
            components_created=components_created,
            components_skipped=components_skipped,
            rule_sets_created=rule_sets_created,
            rule_sets_skipped=rule_sets_skipped,
            brackets_created=brackets_created,
            settings_updated=settings_updated,
            settings_action=settings_action,
            authorities_created=authorities_created,
            authorities_skipped=authorities_skipped,
            mappings_created=mappings_created,
            mappings_skipped=mappings_skipped,
            superseded_previous_pack_code=superseded_previous_pack_code,
            message=" ".join(msg_parts),
        )
