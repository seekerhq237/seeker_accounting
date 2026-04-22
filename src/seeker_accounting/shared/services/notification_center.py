"""In-process notification service.

Notifications are computed fresh from app state on each call — no persistence,
no DB access, no Alembic migration.  The NotificationCenter is consumed by the
topbar bell panel and any other surface that wants app-level alerts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry

NotificationTone = Literal["info", "warning", "danger", "success"]


@dataclass(frozen=True, slots=True)
class AppNotification:
    """A single in-app notification."""

    tone: NotificationTone
    title: str
    body: str
    nav_id: str | None = None  # optional: navigate here on click


class NotificationCenter:
    """Generates in-app notifications from current app state.

    Call ``get_notifications()`` to retrieve the current notification list.
    Results are computed each time; there is no subscription / push model.
    """

    def __init__(self, service_registry: ServiceRegistry) -> None:
        self._sr = service_registry

    # ── Public API ────────────────────────────────────────────────────────

    def get_notifications(self) -> list[AppNotification]:
        """Return all active notifications, ordered by severity (danger first)."""
        result: list[AppNotification] = []
        self._collect_license_notifications(result)
        self._collect_period_notifications(result)
        return result

    # ── Collectors ────────────────────────────────────────────────────────

    def _collect_license_notifications(self, out: list[AppNotification]) -> None:
        try:
            from seeker_accounting.platform.licensing.dto import LicenseState

            info = self._sr.license_service.get_license_info()
            if info.state == LicenseState.TRIAL_EXPIRED:
                out.append(AppNotification(
                    tone="danger",
                    title="Trial expired",
                    body="The trial period has ended. The application is in read-only mode.",
                ))
            elif info.state == LicenseState.LICENSED_EXPIRED:
                out.append(AppNotification(
                    tone="danger",
                    title="License expired",
                    body="Your license has expired. Please renew to restore full access.",
                ))
            elif info.state == LicenseState.TRIAL_ACTIVE and info.trial_days_remaining <= 7:
                out.append(AppNotification(
                    tone="warning",
                    title=f"Trial: {info.trial_days_remaining} day(s) remaining",
                    body="Activate a license key before the trial ends to avoid interruption.",
                ))
        except Exception:
            pass

    def _collect_period_notifications(self, out: list[AppNotification]) -> None:
        company_id = self._sr.active_company_context.company_id
        if not isinstance(company_id, int) or company_id <= 0:
            return
        try:
            period = self._sr.fiscal_calendar_service.get_current_period(company_id)
            if period is None:
                out.append(AppNotification(
                    tone="warning",
                    title="No open fiscal period",
                    body="No open fiscal period for the active company. Posting is blocked.",
                    nav_id="fiscal_periods",
                ))
            elif period.status_code in ("closing", "locked"):
                label = period.status_code.title()
                out.append(AppNotification(
                    tone="warning",
                    title=f"Period {period.period_code} is {label}",
                    body="The current fiscal period is closing or locked. Review before posting.",
                    nav_id="fiscal_periods",
                ))
        except Exception:
            pass
