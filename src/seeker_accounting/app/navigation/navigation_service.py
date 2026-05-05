from __future__ import annotations

from typing import Any, Mapping

from PySide6.QtCore import QObject, Signal

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.platform.exceptions.app_exceptions import NavigationError
from seeker_accounting.shared.services.telemetry_service import (
    TelemetryService,
    get_default_telemetry_service,
)


class NavigationService(QObject):
    navigation_changed = Signal(str)
    navigation_context_changed = Signal(str, object)

    def __init__(
        self,
        initial_nav_id: str = nav_ids.DEFAULT_NAV_ID,
        parent: QObject | None = None,
        telemetry_service: TelemetryService | None = None,
    ) -> None:
        super().__init__(parent)
        if initial_nav_id not in nav_ids.ALL_NAV_IDS:
            raise NavigationError(f"Unknown initial navigation id: {initial_nav_id}")
        self._current_nav_id = initial_nav_id
        self._current_navigation_context: dict[str, Any] = {}
        self._telemetry = telemetry_service or get_default_telemetry_service()

    @property
    def current_nav_id(self) -> str:
        return self._current_nav_id

    @property
    def current_navigation_context(self) -> dict[str, Any]:
        return dict(self._current_navigation_context)

    def navigate(
        self,
        nav_id: str,
        *,
        context: Mapping[str, Any] | None = None,
        resume_token: str | None = None,
        force_emit: bool = False,
    ) -> None:
        if nav_id not in nav_ids.ALL_NAV_IDS:
            raise NavigationError(f"Unknown navigation id: {nav_id}")
        next_context = dict(context or {})
        if resume_token:
            next_context["resume_token"] = resume_token

        nav_id_changed = nav_id != self._current_nav_id
        context_changed = next_context != self._current_navigation_context

        if not nav_id_changed and not context_changed and not force_emit:
            return

        self._current_nav_id = nav_id
        self._current_navigation_context = next_context

        if nav_id_changed or force_emit:
            self.navigation_changed.emit(nav_id)
        self.navigation_context_changed.emit(nav_id, self.current_navigation_context)
        self._record_navigation_telemetry(
            nav_id,
            changed=nav_id_changed,
            has_context=bool(next_context),
            force_emit=force_emit,
        )

    def _record_navigation_telemetry(
        self,
        nav_id: str,
        *,
        changed: bool,
        has_context: bool,
        force_emit: bool,
    ) -> None:
        self._telemetry.record_funnel_step(
            funnel="navigation",
            step="navigate",
            context={
                "nav_id": nav_id,
                "changed": changed,
                "has_context": has_context,
                "force_emit": force_emit,
            },
        )

