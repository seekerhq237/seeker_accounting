from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AuditEventDTO:
    id: int
    company_id: int
    event_type_code: str
    module_code: str
    entity_type: str
    entity_id: int | None
    description: str
    detail_json: str | None
    actor_user_id: int | None
    actor_display_name: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RecordAuditEventCommand:
    """Command to record a single audit event."""
    event_type_code: str
    module_code: str
    entity_type: str
    entity_id: int | None
    description: str
    detail_json: str | None = None
