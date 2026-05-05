"""AuditService — append-only audit event recording and retrieval.

Provides a simple API for business services to record audit events without
managing persistence details. Events are immutable once written.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Mapping

from sqlalchemy.orm import Session

from seeker_accounting.app.context.app_context import AppContext
from seeker_accounting.db.unit_of_work import UnitOfWorkFactory
from seeker_accounting.modules.administration.services.permission_service import PermissionService
from seeker_accounting.modules.audit.dto.audit_event_dto import (
    AuditEventDTO,
    RecordAuditEventCommand,
)
from seeker_accounting.modules.audit.models.audit_event import AuditEvent
from seeker_accounting.modules.audit.repositories.audit_event_repository import (
    AuditEventRepository,
)

AuditEventRepositoryFactory = Callable[[Session], AuditEventRepository]


class AuditService:
    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        app_context: AppContext,
        audit_event_repository_factory: AuditEventRepositoryFactory,
        permission_service: PermissionService | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._app_context = app_context
        self._repo_factory = audit_event_repository_factory
        self._permission_service = permission_service

    def record_event(
        self,
        company_id: int,
        cmd: RecordAuditEventCommand,
    ) -> None:
        """Record one audit event. Commits in its own UoW."""
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            event = AuditEvent(
                company_id=company_id,
                event_type_code=cmd.event_type_code,
                module_code=cmd.module_code,
                entity_type=cmd.entity_type,
                entity_id=cmd.entity_id,
                description=cmd.description,
                detail_json=cmd.detail_json,
                actor_user_id=self._app_context.current_user_id,
                actor_display_name=self._app_context.current_user_display_name,
            )
            repo.save(event)
            uow.commit()

    def record_event_in_session(
        self,
        session: Session,
        company_id: int,
        cmd: RecordAuditEventCommand,
    ) -> None:
        """Record one audit event within an existing session (caller commits)."""
        repo = self._repo_factory(session)
        event = AuditEvent(
            company_id=company_id,
            event_type_code=cmd.event_type_code,
            module_code=cmd.module_code,
            entity_type=cmd.entity_type,
            entity_id=cmd.entity_id,
            description=cmd.description,
            detail_json=cmd.detail_json,
            actor_user_id=self._app_context.current_user_id,
            actor_display_name=self._app_context.current_user_display_name,
        )
        repo.save(event)

    def record_state_transition(
        self,
        company_id: int,
        *,
        module_code: str,
        entity_type: str,
        entity_id: int | None,
        from_state: str | None,
        to_state: str,
        description: str | None = None,
        reason: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        self.record_event(
            company_id,
            self._build_state_transition_command(
                module_code=module_code,
                entity_type=entity_type,
                entity_id=entity_id,
                from_state=from_state,
                to_state=to_state,
                description=description,
                reason=reason,
                context=context,
            ),
        )

    def record_state_transition_in_session(
        self,
        session: Session,
        company_id: int,
        *,
        module_code: str,
        entity_type: str,
        entity_id: int | None,
        from_state: str | None,
        to_state: str,
        description: str | None = None,
        reason: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        self.record_event_in_session(
            session,
            company_id,
            self._build_state_transition_command(
                module_code=module_code,
                entity_type=entity_type,
                entity_id=entity_id,
                from_state=from_state,
                to_state=to_state,
                description=description,
                reason=reason,
                context=context,
            ),
        )

    def record_override_applied(
        self,
        company_id: int,
        *,
        module_code: str,
        entity_type: str,
        entity_id: int | None,
        override_code: str,
        reason: str,
        description: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        self.record_event(
            company_id,
            self._build_override_command(
                module_code=module_code,
                entity_type=entity_type,
                entity_id=entity_id,
                override_code=override_code,
                reason=reason,
                description=description,
                context=context,
            ),
        )

    def record_business_process_step(
        self,
        company_id: int,
        *,
        module_code: str,
        entity_type: str,
        entity_id: int | None,
        process_code: str,
        step_code: str,
        description: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        self.record_event(
            company_id,
            self._build_business_process_step_command(
                module_code=module_code,
                entity_type=entity_type,
                entity_id=entity_id,
                process_code=process_code,
                step_code=step_code,
                description=description,
                context=context,
            ),
        )

    def list_events(
        self,
        company_id: int,
        *,
        module_code: str | None = None,
        event_type_code: str | None = None,
        actor_user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
        required_permission_code: str | None = None,
    ) -> list[AuditEventDTO]:
        self._require_permission(required_permission_code)
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            events = repo.list_by_company(
                company_id,
                module_code=module_code,
                event_type_code=event_type_code,
                actor_user_id=actor_user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                from_date=from_date,
                to_date=to_date,
                limit=limit,
                offset=offset,
            )
            return [self._to_dto(e) for e in events]

    def list_entity_events(
        self,
        company_id: int,
        entity_type: str,
        entity_id: int,
        *,
        limit: int = 200,
        offset: int = 0,
        required_permission_code: str | None = None,
    ) -> list[AuditEventDTO]:
        """Return audit trail for a specific entity."""
        self._require_permission(required_permission_code)
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            events = repo.list_by_entity(
                company_id, entity_type, entity_id,
                limit=limit, offset=offset,
            )
            return [self._to_dto(e) for e in events]

    def count_events(
        self,
        company_id: int,
        *,
        module_code: str | None = None,
        event_type_code: str | None = None,
        actor_user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        required_permission_code: str | None = None,
    ) -> int:
        self._require_permission(required_permission_code)
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            return repo.count_by_company(
                company_id,
                module_code=module_code,
                event_type_code=event_type_code,
                actor_user_id=actor_user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                from_date=from_date,
                to_date=to_date,
            )

    def distinct_module_codes(
        self,
        company_id: int,
        required_permission_code: str | None = None,
    ) -> list[str]:
        self._require_permission(required_permission_code)
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            return repo.distinct_module_codes(company_id)

    def distinct_event_type_codes(
        self,
        company_id: int,
        required_permission_code: str | None = None,
    ) -> list[str]:
        self._require_permission(required_permission_code)
        with self._uow_factory() as uow:
            repo = self._repo_factory(uow.session)
            return repo.distinct_event_type_codes(company_id)

    def _require_permission(self, permission_code: str | None) -> None:
        if permission_code and self._permission_service is not None:
            self._permission_service.require_permission(permission_code)

    @staticmethod
    def _build_state_transition_command(
        *,
        module_code: str,
        entity_type: str,
        entity_id: int | None,
        from_state: str | None,
        to_state: str,
        description: str | None,
        reason: str | None,
        context: Mapping[str, object] | None,
    ) -> RecordAuditEventCommand:
        payload = {
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
            "context": dict(context or {}),
        }
        return RecordAuditEventCommand(
            event_type_code="STATE_TRANSITION",
            module_code=module_code,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description or f"{entity_type} state changed from {from_state or 'none'} to {to_state}.",
            detail_json=json.dumps(payload, sort_keys=True),
        )

    @staticmethod
    def _build_override_command(
        *,
        module_code: str,
        entity_type: str,
        entity_id: int | None,
        override_code: str,
        reason: str,
        description: str | None,
        context: Mapping[str, object] | None,
    ) -> RecordAuditEventCommand:
        payload = {
            "override_code": override_code,
            "reason": reason,
            "context": dict(context or {}),
        }
        return RecordAuditEventCommand(
            event_type_code="OVERRIDE_APPLIED",
            module_code=module_code,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description or f"Override applied: {override_code}.",
            detail_json=json.dumps(payload, sort_keys=True),
        )

    @staticmethod
    def _build_business_process_step_command(
        *,
        module_code: str,
        entity_type: str,
        entity_id: int | None,
        process_code: str,
        step_code: str,
        description: str | None,
        context: Mapping[str, object] | None,
    ) -> RecordAuditEventCommand:
        payload = {
            "process_code": process_code,
            "step_code": step_code,
            "context": dict(context or {}),
        }
        return RecordAuditEventCommand(
            event_type_code="BUSINESS_PROCESS_STEP",
            module_code=module_code,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description or f"Business process step completed: {process_code}.{step_code}.",
            detail_json=json.dumps(payload, sort_keys=True),
        )

    @staticmethod
    def _to_dto(e: AuditEvent) -> AuditEventDTO:
        return AuditEventDTO(
            id=e.id,
            company_id=e.company_id,
            event_type_code=e.event_type_code,
            module_code=e.module_code,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            description=e.description,
            detail_json=e.detail_json,
            actor_user_id=e.actor_user_id,
            actor_display_name=e.actor_display_name,
            created_at=e.created_at,
        )
