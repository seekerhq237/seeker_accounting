"""PayrollAuthorityService — registry of statutory authorities & component map.

Phase 5 / P5.S1.

The authority registry replaces the legacy hardcoded
``{"dgi", "cnps", "other"}`` set inside the remittance flow with a
first-class, company-scoped entity that carries filing cadence, default
GL liability account, and a normalised component-to-authority mapping
used by the remittance auto-seed engine (P5.S3).

Architectural notes:
* This service owns CRUD + validation for ``payroll_authorities`` and
  ``payroll_component_authority_map``.
* It does NOT compute remittance amounts — that lives in
  :mod:`seeker_accounting.modules.payroll.services.payroll_remittance_engine`.
* All writes go through the unit of work; UI must never persist directly.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import (
    PermissionService,
)
from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand
from seeker_accounting.modules.audit.services.audit_service import AuditService
from seeker_accounting.modules.payroll.dto.payroll_authority_dto import (
    ComponentAuthorityMappingDTO,
    CreateComponentAuthorityMappingCommand,
    CreatePayrollAuthorityCommand,
    PayrollAuthorityDTO,
    UpdatePayrollAuthorityCommand,
)
from seeker_accounting.modules.payroll.models.payroll_authority import PayrollAuthority
from seeker_accounting.modules.payroll.models.payroll_component_authority_map import (
    PayrollComponentAuthorityMap,
)
from seeker_accounting.modules.payroll.payroll_permissions import (
    PAYROLL_REMITTANCE_MANAGE,
    PAYROLL_SETUP_MANAGE,
)
from seeker_accounting.modules.payroll.repositories.payroll_authority_repository import (
    PayrollAuthorityRepository,
    PayrollComponentAuthorityMapRepository,
)
from seeker_accounting.modules.payroll.repositories.payroll_component_repository import (
    PayrollComponentRepository,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

_ALLOWED_FILING_CADENCES = frozenset(
    {"monthly", "quarterly", "semi_annual", "annual", "ad_hoc"}
)
_ALLOWED_SIDES = frozenset({"employee", "employer", "total"})
_ALLOWED_LINE_KINDS = frozenset(
    {"contribution", "withholding", "tax", "fee", "surcharge", "other"}
)


class PayrollAuthorityService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authority_repository_factory: Callable[[Session], PayrollAuthorityRepository],
        map_repository_factory: Callable[
            [Session], PayrollComponentAuthorityMapRepository
        ],
        component_repository_factory: Callable[[Session], PayrollComponentRepository],
        permission_service: PermissionService,
        audit_service: AuditService,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._authority_repo_factory = authority_repository_factory
        self._map_repo_factory = map_repository_factory
        self._component_repo_factory = component_repository_factory
        self._permission_service = permission_service
        self._audit_service = audit_service

    # ── Authority CRUD ────────────────────────────────────────────────

    def list_authorities(
        self, company_id: int, *, active_only: bool = False,
    ) -> list[PayrollAuthorityDTO]:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            repo = self._authority_repo_factory(uow.session)
            return [self._to_dto(a) for a in repo.list_by_company(company_id, active_only=active_only)]

    def get_authority(self, company_id: int, authority_id: int) -> PayrollAuthorityDTO:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            repo = self._authority_repo_factory(uow.session)
            authority = repo.get_by_id(company_id, authority_id)
            if authority is None:
                raise NotFoundError("Authority not found.")
            return self._to_dto(authority)

    def create_authority(
        self,
        company_id: int,
        cmd: CreatePayrollAuthorityCommand,
        actor_user_id: int | None = None,
    ) -> PayrollAuthorityDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        code = (cmd.code or "").strip()
        name = (cmd.name or "").strip()
        if not code:
            raise ValidationError("Authority code is required.")
        if not name:
            raise ValidationError("Authority name is required.")
        cadence = (cmd.filing_cadence_code or "monthly").strip().lower()
        if cadence not in _ALLOWED_FILING_CADENCES:
            raise ValidationError(
                f"Invalid filing cadence '{cadence}'. Allowed: "
                f"{', '.join(sorted(_ALLOWED_FILING_CADENCES))}"
            )
        if cmd.deadline_day is not None and not (1 <= cmd.deadline_day <= 31):
            raise ValidationError("Deadline day must be between 1 and 31.")

        with self._uow_factory() as uow:
            repo = self._authority_repo_factory(uow.session)
            if repo.get_by_code(company_id, code) is not None:
                raise ConflictError(f"Authority with code '{code}' already exists.")
            authority = PayrollAuthority(
                company_id=company_id,
                code=code,
                name=name,
                jurisdiction_code=cmd.jurisdiction_code,
                filing_cadence_code=cadence,
                deadline_rule_code=cmd.deadline_rule_code,
                deadline_day=cmd.deadline_day,
                gl_liability_account_id=cmd.gl_liability_account_id,
                notes=cmd.notes,
                is_active=True,
            )
            repo.save(authority)
            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_AUTHORITY_CREATED",
                    module_code="payroll",
                    entity_type="payroll_authority",
                    entity_id=authority.id,
                    description=f"Created payroll authority '{authority.code}'.",
                    detail_json=json.dumps({"code": authority.code, "name": authority.name}),
                ),
            )
            uow.commit()
            return self._to_dto(authority)

    def update_authority(
        self,
        company_id: int,
        authority_id: int,
        cmd: UpdatePayrollAuthorityCommand,
        actor_user_id: int | None = None,
    ) -> PayrollAuthorityDTO:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._uow_factory() as uow:
            repo = self._authority_repo_factory(uow.session)
            authority = repo.get_by_id(company_id, authority_id)
            if authority is None:
                raise NotFoundError("Authority not found.")

            changes: dict[str, object] = {}
            if cmd.name is not None:
                name = cmd.name.strip()
                if not name:
                    raise ValidationError("Authority name cannot be empty.")
                if name != authority.name:
                    changes["name"] = name
                    authority.name = name
            if cmd.jurisdiction_code is not None and cmd.jurisdiction_code != authority.jurisdiction_code:
                authority.jurisdiction_code = cmd.jurisdiction_code or None
                changes["jurisdiction_code"] = authority.jurisdiction_code
            if cmd.filing_cadence_code is not None:
                cadence = cmd.filing_cadence_code.strip().lower()
                if cadence not in _ALLOWED_FILING_CADENCES:
                    raise ValidationError(
                        f"Invalid filing cadence '{cadence}'."
                    )
                if cadence != authority.filing_cadence_code:
                    authority.filing_cadence_code = cadence
                    changes["filing_cadence_code"] = cadence
            if cmd.deadline_rule_code is not None and cmd.deadline_rule_code != authority.deadline_rule_code:
                authority.deadline_rule_code = cmd.deadline_rule_code or None
                changes["deadline_rule_code"] = authority.deadline_rule_code
            if cmd.deadline_day is not None and cmd.deadline_day != authority.deadline_day:
                if not (1 <= cmd.deadline_day <= 31):
                    raise ValidationError("Deadline day must be between 1 and 31.")
                authority.deadline_day = cmd.deadline_day
                changes["deadline_day"] = cmd.deadline_day
            if cmd.gl_liability_account_id is not None and cmd.gl_liability_account_id != authority.gl_liability_account_id:
                authority.gl_liability_account_id = cmd.gl_liability_account_id
                changes["gl_liability_account_id"] = cmd.gl_liability_account_id
            if cmd.is_active is not None and bool(cmd.is_active) != bool(authority.is_active):
                authority.is_active = bool(cmd.is_active)
                changes["is_active"] = authority.is_active
            if cmd.notes is not None and cmd.notes != authority.notes:
                authority.notes = cmd.notes or None
                changes["notes"] = authority.notes

            if changes:
                self._audit_service.record_event_in_session(
                    uow.session,
                    company_id,
                    RecordAuditEventCommand(
                        event_type_code="PAYROLL_AUTHORITY_UPDATED",
                        module_code="payroll",
                        entity_type="payroll_authority",
                        entity_id=authority.id,
                        description=f"Updated payroll authority '{authority.code}'.",
                        detail_json=json.dumps({"changes": changes}, default=str),
                    ),
                )
            uow.commit()
            return self._to_dto(authority)

    def deactivate_authority(
        self,
        company_id: int,
        authority_id: int,
        actor_user_id: int | None = None,
    ) -> PayrollAuthorityDTO:
        return self.update_authority(
            company_id,
            authority_id,
            UpdatePayrollAuthorityCommand(is_active=False),
            actor_user_id=actor_user_id,
        )

    # ── Component-authority mapping ───────────────────────────────────

    def list_mappings(
        self,
        company_id: int,
        *,
        component_id: int | None = None,
        authority_id: int | None = None,
    ) -> list[ComponentAuthorityMappingDTO]:
        self._permission_service.require_permission(PAYROLL_REMITTANCE_MANAGE)
        with self._uow_factory() as uow:
            repo = self._map_repo_factory(uow.session)
            mappings = repo.list_by_company(
                company_id, component_id=component_id, authority_id=authority_id,
            )
            return [self._to_mapping_dto(m) for m in mappings]

    def set_mapping(
        self,
        company_id: int,
        cmd: CreateComponentAuthorityMappingCommand,
        actor_user_id: int | None = None,
    ) -> ComponentAuthorityMappingDTO:
        """Upsert a component → authority mapping by (component, authority, side)."""
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        side = (cmd.side or "total").strip().lower()
        if side not in _ALLOWED_SIDES:
            raise ValidationError(
                f"Invalid side '{side}'. Allowed: {', '.join(sorted(_ALLOWED_SIDES))}"
            )
        line_kind = (cmd.line_kind or "contribution").strip().lower()
        if line_kind not in _ALLOWED_LINE_KINDS:
            raise ValidationError(
                f"Invalid line kind '{line_kind}'. Allowed: "
                f"{', '.join(sorted(_ALLOWED_LINE_KINDS))}"
            )
        if cmd.fraction is None or cmd.fraction <= Decimal("0"):
            raise ValidationError("Fraction must be greater than zero.")
        if cmd.fraction > Decimal("1"):
            raise ValidationError("Fraction must be less than or equal to 1.0.")

        with self._uow_factory() as uow:
            comp = self._component_repo_factory(uow.session).get_by_id(
                company_id, cmd.component_id,
            )
            if comp is None:
                raise NotFoundError("Payroll component not found.")
            authority_repo = self._authority_repo_factory(uow.session)
            authority = authority_repo.get_by_id(company_id, cmd.authority_id)
            if authority is None:
                raise NotFoundError("Authority not found.")

            map_repo = self._map_repo_factory(uow.session)
            existing = map_repo.find(
                company_id,
                component_id=cmd.component_id,
                authority_id=cmd.authority_id,
                side=side,
            )
            event_code: str
            if existing is None:
                mapping = PayrollComponentAuthorityMap(
                    company_id=company_id,
                    component_id=cmd.component_id,
                    authority_id=cmd.authority_id,
                    side=side,
                    line_kind=line_kind,
                    fraction=cmd.fraction,
                )
                map_repo.save(mapping)
                event_code = "PAYROLL_AUTHORITY_MAPPING_CREATED"
            else:
                existing.line_kind = line_kind
                existing.fraction = cmd.fraction
                mapping = existing
                event_code = "PAYROLL_AUTHORITY_MAPPING_UPDATED"

            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code=event_code,
                    module_code="payroll",
                    entity_type="payroll_component_authority_map",
                    entity_id=mapping.id,
                    description=(
                        f"Mapped component '{comp.component_code}' → "
                        f"authority '{authority.code}' (side={side})."
                    ),
                    detail_json=json.dumps(
                        {
                            "component_id": mapping.component_id,
                            "authority_id": mapping.authority_id,
                            "side": side,
                            "line_kind": line_kind,
                            "fraction": str(cmd.fraction),
                        }
                    ),
                ),
            )
            uow.commit()
            return self._to_mapping_dto(mapping)

    def delete_mapping(
        self,
        company_id: int,
        mapping_id: int,
        actor_user_id: int | None = None,
    ) -> None:
        self._permission_service.require_permission(PAYROLL_SETUP_MANAGE)
        with self._uow_factory() as uow:
            map_repo = self._map_repo_factory(uow.session)
            mapping = map_repo.get_by_id(company_id, mapping_id)
            if mapping is None:
                raise NotFoundError("Mapping not found.")
            comp_code = mapping.component.component_code if mapping.component else "?"
            auth_code = mapping.authority.code if mapping.authority else "?"
            map_repo.delete(mapping)
            uow.session.flush()
            self._audit_service.record_event_in_session(
                uow.session,
                company_id,
                RecordAuditEventCommand(
                    event_type_code="PAYROLL_AUTHORITY_MAPPING_DELETED",
                    module_code="payroll",
                    entity_type="payroll_component_authority_map",
                    entity_id=mapping_id,
                    description=(
                        f"Removed mapping component '{comp_code}' → authority '{auth_code}'."
                    ),
                ),
            )
            uow.commit()

    # ── DTO conversion ────────────────────────────────────────────────

    @staticmethod
    def _to_dto(authority: PayrollAuthority) -> PayrollAuthorityDTO:
        return PayrollAuthorityDTO(
            id=authority.id,
            company_id=authority.company_id,
            code=authority.code,
            name=authority.name,
            jurisdiction_code=authority.jurisdiction_code,
            filing_cadence_code=authority.filing_cadence_code,
            deadline_rule_code=authority.deadline_rule_code,
            deadline_day=authority.deadline_day,
            gl_liability_account_id=authority.gl_liability_account_id,
            is_active=bool(authority.is_active),
            notes=authority.notes,
        )

    @staticmethod
    def _to_mapping_dto(
        mapping: PayrollComponentAuthorityMap,
    ) -> ComponentAuthorityMappingDTO:
        return ComponentAuthorityMappingDTO(
            id=mapping.id,
            company_id=mapping.company_id,
            component_id=mapping.component_id,
            component_code=mapping.component.component_code if mapping.component else "",
            component_name=mapping.component.component_name if mapping.component else "",
            authority_id=mapping.authority_id,
            authority_code=mapping.authority.code if mapping.authority else "",
            authority_name=mapping.authority.name if mapping.authority else "",
            side=mapping.side,
            line_kind=mapping.line_kind,
            fraction=Decimal(mapping.fraction) if mapping.fraction is not None else Decimal("0"),
        )
