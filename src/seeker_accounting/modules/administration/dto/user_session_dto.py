from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UserSessionDTO:
    id: int
    user_id: int
    user_display_name: str
    company_id: int
    login_at: datetime
    logout_at: datetime | None
    logout_reason: str | None
    abnormal_explanation_code: str | None
    abnormal_explanation_note: str | None
    abnormal_reviewed_by_user_id: int | None
    abnormal_reviewed_at: datetime | None
    app_version: str | None
    hostname: str | None
    os_info: str | None


# Abnormal explanation codes — used in AbnormalShutdownDialog and service layer.
EXPLANATION_POWER_OUTAGE = "power_outage"
EXPLANATION_APP_NOT_RESPONDING = "app_not_responding"
EXPLANATION_COMPUTER_CRASHED = "computer_crashed"
EXPLANATION_FORCED_CLOSE = "forced_close"
EXPLANATION_NETWORK_ISSUE = "network_issue"
EXPLANATION_OTHER = "other"

ABNORMAL_EXPLANATION_CHOICES: list[tuple[str, str]] = [
    (EXPLANATION_POWER_OUTAGE, "Power outage"),
    (EXPLANATION_APP_NOT_RESPONDING, "Application stopped responding"),
    (EXPLANATION_COMPUTER_CRASHED, "Computer crashed or restarted unexpectedly"),
    (EXPLANATION_FORCED_CLOSE, "Forced close (e.g. Task Manager)"),
    (EXPLANATION_NETWORK_ISSUE, "Internet / network issue"),
    (EXPLANATION_OTHER, "Other"),
]

# Codes that indicate a potential software defect — admin should be notified.
REQUIRES_ADMIN_ATTENTION_CODES = frozenset({
    EXPLANATION_APP_NOT_RESPONDING,
    EXPLANATION_COMPUTER_CRASHED,
})
