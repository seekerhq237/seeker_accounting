"""DTOs and status codes for wizard run persistence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class WizardRunStatusCode(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class WizardRunDTO:
    id: int
    wizard_code: str
    company_id: int | None
    initiated_by_user_id: int
    current_step_index: int
    current_step_key: str | None
    status_code: str
    state_payload: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(slots=True, frozen=True)
class WizardRunListItemDTO:
    id: int
    wizard_code: str
    company_id: int | None
    current_step_index: int
    current_step_key: str | None
    status_code: str
    updated_at: datetime
