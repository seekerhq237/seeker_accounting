"""Bridge pane that hands the user off to a legacy payroll page.

Phase 2 ships the new sidebar entry and shell. Slices S3–S7 will fill
each of the rebuilt panes with first-class workbench content. Until
those slices land, panes that are not yet rebuilt show a calm
:class:`EmptyState` with a clear "Open in classic view" action that
navigates to the corresponding legacy page through
:class:`NavigationService`.

This is intentionally not a wrapper around the legacy widget — those
widgets carry their own ribbons and topbars and would not feel native
inside the workbench shell.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.components import EmptyState

logger = logging.getLogger(__name__)


class LegacyLinkPane(QFrame):
    def __init__(
        self,
        *,
        service_registry: ServiceRegistry,
        headline: str,
        body: str,
        primary_label: str,
        primary_nav_id: str,
        secondary_label: str | None = None,
        secondary_nav_id: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollWorkbenchLegacyLinkPane")
        self._sr = service_registry
        self._primary_nav_id = primary_nav_id
        self._secondary_nav_id = secondary_nav_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty = EmptyState(
            headline=headline,
            body=body,
            primary_label=primary_label,
            secondary_label=secondary_label,
            glyph="↗",
            parent=self,
        )
        empty.primary_clicked.connect(self._open_primary)
        if secondary_nav_id is not None:
            empty.secondary_clicked.connect(self._open_secondary)
        layout.addWidget(empty)

    def _open_primary(self) -> None:
        self._navigate(self._primary_nav_id)

    def _open_secondary(self) -> None:
        if self._secondary_nav_id is not None:
            self._navigate(self._secondary_nav_id)

    def _navigate(self, nav_id: str) -> None:
        nav_svc: Any | None = getattr(self._sr, "navigation_service", None)
        if nav_svc is None:
            logger.warning("navigation_service not available; cannot route to %s", nav_id)
            return
        try:
            nav_svc.navigate(nav_id)
        except Exception:  # pragma: no cover — defensive
            logger.exception("navigate(%s) failed", nav_id)
