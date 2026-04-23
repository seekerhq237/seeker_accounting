"""
RibbonBar — context-aware single ribbon band hosted in MainWindow.

The bar keeps a ``QStackedWidget`` of cached :class:`RibbonSurface`
instances (one per registered surface key). :meth:`set_context` swaps
the visible surface and connects its clicks to the active host through
the :class:`RibbonActionDispatcher`.

The bar hides itself entirely when no surface is registered for the
current context — this preserves clean layouts for pages that deliberately
don't use a ribbon yet.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QStackedWidget, QVBoxLayout, QWidget

from seeker_accounting.app.shell.ribbon.ribbon_actions import RibbonActionDispatcher
from seeker_accounting.app.shell.ribbon.ribbon_host import IRibbonHost
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.app.shell.ribbon.ribbon_surface import RibbonSurface
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


class RibbonBar(QFrame):
    """Context-aware ribbon host."""

    def __init__(
        self,
        registry: RibbonRegistry,
        icon_provider: IconProvider,
        dispatcher: RibbonActionDispatcher,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._icon_provider = icon_provider
        self._dispatcher = dispatcher
        self._surfaces: dict[str, RibbonSurface] = {}
        self._active_host: IRibbonHost | None = None
        self._current_surface_key: str | None = None

        self.setObjectName("RibbonBar")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(DEFAULT_TOKENS.sizes.ribbon_height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("RibbonStack")
        layout.addWidget(self._stack)

        # Empty placeholder so the stack always has at least one widget.
        self._placeholder = QWidget(self)
        self._placeholder.setObjectName("RibbonPlaceholder")
        self._stack.addWidget(self._placeholder)

        self.hide()

    # ── Public API ────────────────────────────────────────────────────

    def set_context(
        self,
        surface_key: str | None,
        host: IRibbonHost | None = None,
    ) -> None:
        """
        Activate the ribbon surface for *surface_key* and bind *host*.

        Passing ``None`` (or an unregistered key) hides the ribbon.
        """

        if not surface_key:
            self._apply_empty_context()
            return

        surface_def = self._registry.get(surface_key)
        if surface_def is None:
            self._apply_empty_context()
            return

        surface = self._surfaces.get(surface_key)
        if surface is None:
            surface = RibbonSurface(surface_def, self._icon_provider, self)
            surface.command_activated.connect(self._dispatcher.dispatch)
            self._stack.addWidget(surface)
            self._surfaces[surface_key] = surface

        self._stack.setCurrentWidget(surface)
        self._current_surface_key = surface_key

        # Wire host & apply enablement.
        self._active_host = host if isinstance(host, IRibbonHost) else None
        self._dispatcher.set_active_host(self._active_host)
        self._apply_host_state(surface)

        self.show()

    def refresh_active_state(self) -> None:
        """Re-pull ``ribbon_state()`` from the active host (e.g. after selection)."""
        if self._current_surface_key is None:
            return
        surface = self._surfaces.get(self._current_surface_key)
        if surface is not None:
            self._apply_host_state(surface)

    def refresh_icons(self) -> None:
        """Force icon redraw on theme change."""
        for surface in self._surfaces.values():
            surface.refresh_icons()

    # ── Internals ─────────────────────────────────────────────────────

    def _apply_empty_context(self) -> None:
        self._current_surface_key = None
        self._active_host = None
        self._dispatcher.set_active_host(None)
        self._stack.setCurrentWidget(self._placeholder)
        self.hide()

    def _apply_host_state(self, surface: RibbonSurface) -> None:
        surface.reset_enablement_to_defaults()
        host = self._active_host
        if host is None:
            return
        try:
            state = host.ribbon_state()
        except Exception:
            # Never let a host bug bring down the ribbon.
            return
        if state:
            surface.set_enablement(state)
