from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class GuidedResolutionSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(slots=True)
class GuidedResolutionAction:
    action_id: str
    label: str
    nav_id: str | None = None
    close_dialog: bool = True
    requires_resume_token: bool = False
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class GuidedResolution:
    resolution_code: str
    error_code: str
    title: str
    message: str
    severity: GuidedResolutionSeverity = GuidedResolutionSeverity.WARNING
    actions: list[GuidedResolutionAction] = field(default_factory=list)
    details: str | None = None
    debug_details: str | None = None


@dataclass(slots=True)
class ResumeTokenPayload:
    workflow_key: str
    origin_nav_id: str | None
    payload: dict[str, Any]
    created_at: datetime
