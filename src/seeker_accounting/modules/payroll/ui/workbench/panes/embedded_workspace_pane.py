"""Embedded workspace pane.

Phase 2 deferral S3-S7: rather than rebuild every payroll surface from
scratch in this slice, host the *existing* payroll workspaces inside the
workbench. This delivers the IA reset (single sidebar entry, single
shell, single navigation) while preserving every action that previously
lived under the four legacy nav IDs.

The deeper redesigns (master+detail People, side-by-side Compensation,
sectioned Setup, single-page Statutory editor) remain as future slices
(Phase 3 / Phase 4 / Phase 5) and will replace these embeds in turn.
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.components import EmptyState

logger = logging.getLogger(__name__)


WidgetFactory = Callable[[ServiceRegistry, QWidget], QWidget]


class EmbeddedWorkspacePane(QFrame):
    """Container that hosts a single existing workspace widget.

    The wrapped widget is constructed lazily on first paint via the
    supplied ``factory``. Initialization failures (e.g. permission
    denied, services unavailable) degrade to a calm
    :class:`EmptyState` rather than crashing the workbench.

    Parameters
    ----------
    service_registry:
        Dependency container forwarded to the factory.
    factory:
        Callable that builds the inner widget. Receives
        ``(service_registry, parent)``.
    fallback_headline / fallback_body / fallback_glyph:
        Copy used when the factory raises. ``fallback_glyph`` defaults
        to ``"—"``.
    select_tab_index:
        Optional 0-based index. After the inner widget is built, if it
        exposes a ``QTabWidget`` attribute called ``_tabs`` (the
        established convention across the existing payroll
        workspaces), the requested tab is selected. Out-of-range
        indexes are silently ignored.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        factory: WidgetFactory,
        *,
        fallback_headline: str = "This workspace is unavailable",
        fallback_body: str = (
            "The underlying service is not reachable for the current user."
        ),
        fallback_glyph: str = "—",
        select_tab_index: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PayrollWorkbenchEmbeddedPane")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._sr = service_registry
        self._factory = factory
        self._fallback_headline = fallback_headline
        self._fallback_body = fallback_body
        self._fallback_glyph = fallback_glyph
        self._select_tab_index = select_tab_index

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._inner: QWidget | None = None
        try:
            self._inner = factory(service_registry, self)
        except Exception:  # pragma: no cover — defensive
            logger.warning(
                "EmbeddedWorkspacePane factory failed: %s",
                fallback_headline,
                exc_info=True,
            )
            self._inner = None

        if self._inner is None:
            empty = EmptyState(
                headline=fallback_headline,
                body=fallback_body,
                glyph=fallback_glyph,
            )
            layout.addStretch(1)
            layout.addWidget(empty, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addStretch(1)
            return

        layout.addWidget(self._inner)

        if select_tab_index is not None:
            tabs = getattr(self._inner, "_tabs", None)
            try:
                from PySide6.QtWidgets import QTabWidget

                if isinstance(tabs, QTabWidget) and 0 <= select_tab_index < tabs.count():
                    tabs.setCurrentIndex(select_tab_index)
            except Exception:  # pragma: no cover — defensive
                logger.debug(
                    "EmbeddedWorkspacePane could not pre-select tab %s",
                    select_tab_index,
                    exc_info=True,
                )

    # Convenience accessor for tests.
    def inner_widget(self) -> QWidget | None:
        return self._inner
