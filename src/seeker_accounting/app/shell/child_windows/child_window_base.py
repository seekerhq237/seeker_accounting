"""
ChildWindowBase — base class for top-level document child windows.

A child window is a ``Qt.Window`` that lives outside the main shell's
workspace stack. It has its own OS chrome, its own taskbar entry, and is
freely movable across monitors. Each child window paints its own ribbon
at the top and its module-provided body below.

This base purposely stays thin: concrete child windows (e.g. the journal
entry window) supply the ribbon surface key, the body widget, the save /
discard hooks, and the dirty tracking.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.shell.ribbon.ribbon_actions import RibbonActionDispatcher
from seeker_accounting.app.shell.ribbon.ribbon_host import IRibbonHost
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.app.shell.ribbon.ribbon_surface import RibbonSurface
from seeker_accounting.shared.ui.icon_provider import IconProvider


class ChildWindowBase(QWidget):
    """
    Top-level document window base.

    Subclasses must:

    * provide ``surface_key`` (e.g. ``"child:journal_entry"``);
    * provide ``window_key`` — the ``(doc_type, entity_id)`` pair used
      by :class:`ChildWindowManager` to dedupe;
    * implement :meth:`handle_ribbon_command` (from IRibbonHost);
    * implement :meth:`ribbon_state` (from IRibbonHost).

    The body widget is installed via :meth:`set_body`.
    """

    #: Emitted after the window accepts close. Payload: ``window_key``.
    closed = Signal(object)
    #: Dirty-flag changes. Payload: ``bool``.
    dirty_changed = Signal(bool)

    def __init__(
        self,
        *,
        title: str,
        surface_key: str,
        window_key: tuple[str, object | None],
        registry: RibbonRegistry,
        icon_provider: IconProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("ChildWindowRoot")
        self.setWindowTitle(title)
        self.resize(1080, 720)

        self._window_key = window_key
        self._surface_key = surface_key
        self._dirty = False

        # Local ribbon (independent of main shell's ribbon).
        self._dispatcher = RibbonActionDispatcher()
        self._dispatcher.set_active_host(self)  # self IS the host

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._ribbon_host = QFrame(self)
        self._ribbon_host.setObjectName("ChildWindowRibbonHost")
        ribbon_host_layout = QVBoxLayout(self._ribbon_host)
        ribbon_host_layout.setContentsMargins(0, 0, 0, 0)
        ribbon_host_layout.setSpacing(0)

        surface_def = registry.get(surface_key)
        if surface_def is not None:
            self._ribbon_surface: RibbonSurface | None = RibbonSurface(
                surface_def, icon_provider, self._ribbon_host
            )
            self._ribbon_surface.command_activated.connect(self._dispatcher.dispatch)
            ribbon_host_layout.addWidget(self._ribbon_surface)
            self._ribbon_host.setFixedHeight(
                self._ribbon_surface.sizeHint().height() + 4
            )
        else:
            self._ribbon_surface = None
            self._ribbon_host.hide()

        root.addWidget(self._ribbon_host)

        self._body_host = QFrame(self)
        self._body_host.setObjectName("ChildWindowBody")
        self._body_layout = QVBoxLayout(self._body_host)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        root.addWidget(self._body_host, 1)

    # ── Public API ────────────────────────────────────────────────────

    @property
    def window_key(self) -> tuple[str, object | None]:
        return self._window_key

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_body(self, widget: QWidget) -> None:
        # Clear any existing body widgets.
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
        self._body_layout.addWidget(widget)

    def set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)
        title = self.windowTitle()
        if dirty and not title.startswith("● "):
            self.setWindowTitle(f"● {title}")
        elif not dirty and title.startswith("● "):
            self.setWindowTitle(title[2:])

    def refresh_ribbon_state(self) -> None:
        if self._ribbon_surface is None:
            return
        self._ribbon_surface.reset_enablement_to_defaults()
        try:
            state = self.ribbon_state()
        except Exception:
            return
        if state:
            self._ribbon_surface.set_enablement(state)

    # ── IRibbonHost (default no-op) ───────────────────────────────────

    def handle_ribbon_command(self, command_id: str) -> None:  # pragma: no cover
        # Generic close command handled here; subclasses override for the rest.
        if command_id.endswith(".close"):
            self.close()

    def ribbon_state(self):  # -> Mapping[str, bool]
        return {}

    # ── Dirty-aware close ─────────────────────────────────────────────

    def save(self) -> bool:
        """Subclasses override. Return ``True`` if save succeeded."""
        return True

    def discard(self) -> None:
        """Subclasses override to roll back in-memory changes."""
        return None

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self._dirty:
            choice = QMessageBox.question(
                self,
                "Unsaved changes",
                "This window has unsaved changes.\n\n"
                "Save your changes before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if choice == QMessageBox.StandardButton.Save:
                if not self.save():
                    event.ignore()
                    return
            else:
                self.discard()

        self.closed.emit(self._window_key)
        super().closeEvent(event)


__all__ = ["ChildWindowBase", "IRibbonHost"]
