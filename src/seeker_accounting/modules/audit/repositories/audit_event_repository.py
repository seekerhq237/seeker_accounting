from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seeker_accounting.modules.audit.models.audit_event import AuditEvent


class AuditEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, event: AuditEvent) -> None:
        self._session.add(event)

    def list_by_company(
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
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.company_id == company_id)
            .order_by(AuditEvent.created_at.desc())
        )
        stmt = self._apply_filters(
            stmt,
            module_code=module_code,
            event_type_code=event_type_code,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            from_date=from_date,
            to_date=to_date,
        )
        stmt = stmt.offset(offset).limit(limit)
        return list(self._session.scalars(stmt).all())

    def list_by_entity(
        self,
        company_id: int,
        entity_type: str,
        entity_id: int,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """Return audit trail for a single entity."""
        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.company_id == company_id,
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            .order_by(AuditEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())

    def count_by_company(
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
    ) -> int:
        stmt = select(func.count(AuditEvent.id)).where(
            AuditEvent.company_id == company_id,
        )
        stmt = self._apply_filters(
            stmt,
            module_code=module_code,
            event_type_code=event_type_code,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            from_date=from_date,
            to_date=to_date,
        )
        return self._session.scalar(stmt) or 0

    def distinct_module_codes(self, company_id: int) -> list[str]:
        """Return sorted list of distinct module codes for filter dropdowns."""
        stmt = (
            select(AuditEvent.module_code)
            .where(AuditEvent.company_id == company_id)
            .distinct()
            .order_by(AuditEvent.module_code)
        )
        return list(self._session.scalars(stmt).all())

    def distinct_event_type_codes(self, company_id: int) -> list[str]:
        """Return sorted list of distinct event type codes for filter dropdowns."""
        stmt = (
            select(AuditEvent.event_type_code)
            .where(AuditEvent.company_id == company_id)
            .distinct()
            .order_by(AuditEvent.event_type_code)
        )
        return list(self._session.scalars(stmt).all())

    # ── internal ──────────────────────────────────────────────────────

    @staticmethod
    def _apply_filters(
        stmt,
        *,
        module_code: str | None,
        event_type_code: str | None,
        actor_user_id: int | None,
        entity_type: str | None,
        entity_id: int | None,
        from_date: datetime | None,
        to_date: datetime | None,
    ):
        if module_code:
            stmt = stmt.where(AuditEvent.module_code == module_code)
        if event_type_code:
            stmt = stmt.where(AuditEvent.event_type_code == event_type_code)
        if actor_user_id is not None:
            stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
        if entity_type:
            stmt = stmt.where(AuditEvent.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditEvent.entity_id == entity_id)
        if from_date is not None:
            stmt = stmt.where(AuditEvent.created_at >= from_date)
        if to_date is not None:
            stmt = stmt.where(AuditEvent.created_at <= to_date)
        return stmt
