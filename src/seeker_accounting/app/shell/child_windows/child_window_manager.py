"""
ChildWindowManager — dedupe + track top-level document windows.

Subsystems that want to open a document window call
:meth:`open_document` with ``(doc_type, entity_id)``. If a matching window
is already open, it is raised and activated. Otherwise, the caller's
``factory`` is invoked to construct a fresh :class:`ChildWindowBase`.

The manager is registered on the :class:`ServiceRegistry` so pages can
reach it from anywhere in the UI tree.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from seeker_accounting.app.shell.child_windows.child_window_base import (
    ChildWindowBase,
)


ChildWindowFactory = Callable[[], ChildWindowBase]


class ChildWindowManager(QObject):
    """Single-instance registry of live document windows."""

    #: Emitted whenever a window is opened or closed.
    windows_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._windows: dict[tuple[str, object | None], ChildWindowBase] = {}

    # ── Public API ────────────────────────────────────────────────────

    def open_document(
        self,
        doc_type: str,
        entity_id: object | None,
        factory: ChildWindowFactory,
    ) -> ChildWindowBase:
        """
        Open or raise the window for ``(doc_type, entity_id)``.

        ``entity_id`` may be ``None`` for new-unsaved documents; in that
        case a fresh window is created every call (no dedupe).
        """

        if entity_id is not None:
            key = (doc_type, entity_id)
            existing = self._windows.get(key)
            if existing is not None:
                self._activate(existing)
                return existing
        else:
            key = (doc_type, id(factory))  # ensure uniqueness for fresh windows

        window = factory()
        self._windows[key] = window
        window.closed.connect(self._on_closed)
        window.show()
        self._activate(window)
        self.windows_changed.emit()
        return window

    def is_open(self, doc_type: str, entity_id: object) -> bool:
        return (doc_type, entity_id) in self._windows

    def get(self, doc_type: str, entity_id: object) -> ChildWindowBase | None:
        return self._windows.get((doc_type, entity_id))

    def all_windows(self) -> tuple[ChildWindowBase, ...]:
        return tuple(self._windows.values())

    def close_all(self) -> None:
        for window in list(self._windows.values()):
            window.close()

    # ── Internals ─────────────────────────────────────────────────────

    def _activate(self, window: ChildWindowBase) -> None:
        window.raise_()
        window.activateWindow()

    def _on_closed(self, window_key: object) -> None:
        # Remove by identity of the key reported back to us.
        for key, win in list(self._windows.items()):
            if key == window_key or win.window_key == window_key:
                self._windows.pop(key, None)
        self.windows_changed.emit()
