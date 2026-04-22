from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.navigation.navigation_service import NavigationService
from seeker_accounting.app.navigation.workflow_resume_service import WorkflowResumeService
from seeker_accounting.platform.exceptions.error_resolution import (
    GuidedResolution,
    GuidedResolutionAction,
)
from seeker_accounting.platform.exceptions.error_resolution_resolver import ErrorResolutionResolver
from seeker_accounting.shared.ui.guided_resolution_dialog import GuidedResolutionDialog


@dataclass(slots=True)
class GuidedResolutionResult:
    handled: bool
    resolution: GuidedResolution | None
    selected_action: GuidedResolutionAction | None
    resume_token: str | None


class GuidedResolutionCoordinator:
    """Coordinates resolution mapping, resume-token capture, and guided dialog display."""

    def __init__(
        self,
        resolver: ErrorResolutionResolver,
        workflow_resume_service: WorkflowResumeService,
        navigation_service: NavigationService,
    ) -> None:
        self._resolver = resolver
        self._workflow_resume_service = workflow_resume_service
        self._navigation_service = navigation_service

    def handle_exception(
        self,
        *,
        parent: QWidget | None,
        error: Exception,
        workflow_key: str | None = None,
        workflow_snapshot: Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None = None,
        origin_nav_id: str | None = None,
        resolution_context: Mapping[str, Any] | None = None,
    ) -> GuidedResolutionResult:
        resolution = self._resolver.resolve(error, resolution_context)
        if resolution is None:
            return GuidedResolutionResult(
                handled=False,
                resolution=None,
                selected_action=None,
                resume_token=None,
            )

        dialog = GuidedResolutionDialog(resolution=resolution, parent=parent)
        dialog.exec()
        selected_action = dialog.selected_action

        resume_token: str | None = None
        if selected_action and selected_action.requires_resume_token:
            snapshot_payload = self._materialize_snapshot(workflow_snapshot)
            if workflow_key and snapshot_payload is not None:
                resume_token = self._workflow_resume_service.create_token(
                    workflow_key=workflow_key,
                    origin_nav_id=origin_nav_id,
                    payload=dict(snapshot_payload),
                )

        if selected_action and selected_action.nav_id:
            self._navigation_service.navigate(
                selected_action.nav_id,
                context=selected_action.payload,
                resume_token=resume_token,
            )

        return GuidedResolutionResult(
            handled=True,
            resolution=resolution,
            selected_action=selected_action,
            resume_token=resume_token,
        )

    def _materialize_snapshot(
        self,
        workflow_snapshot: Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None,
    ) -> Mapping[str, Any] | None:
        if workflow_snapshot is None:
            return None
        if callable(workflow_snapshot):
            return workflow_snapshot()
        return workflow_snapshot
