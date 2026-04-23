"""
RibbonHostMixin — reusable plumbing for pages that act as IRibbonHost.

Pages participating in the context-aware ribbon typically need:

* a stable way to dispatch a string ``command_id`` to a page method,
* an ``enablement`` map matching the page's action state,
* a hook to notify the currently-visible :class:`RibbonBar` that the
  page's ribbon state changed (e.g. on selection change).

This mixin wraps those three concerns so individual pages can focus on
the business logic (which commands exist, which are enabled right now,
what to do when one fires).

Usage::

    class MyPage(RibbonHostMixin, QWidget):
        def _ribbon_commands(self) -> Mapping[str, Callable[[], None]]:
            return {
                "mydoc.new": self._open_create_dialog,
                "mydoc.edit": self._open_edit_dialog,
                ...
            }

        def ribbon_state(self) -> Mapping[str, bool]:
            return {"mydoc.edit": self._has_draft_selected(), ...}

    # and at the tail of whatever updates action enablement:
    self._notify_ribbon_state_changed()

The mixin deliberately does not own *when* to notify — that remains
explicit in the page, wired to selection changes and data reloads.
"""

from __future__ import annotations

from typing import Callable, Mapping

from PySide6.QtWidgets import QWidget


class RibbonHostMixin:
    """Mixin providing :class:`IRibbonHost` plumbing for pages/windows."""

    # Subclasses override.
    def _ribbon_commands(self) -> Mapping[str, Callable[[], None]]:
        return {}

    def ribbon_state(self) -> Mapping[str, bool]:
        return {}

    def current_ribbon_surface_key(self) -> str | None:
        """Optional hook for hosts whose ribbon surface changes with context."""
        return None

    # ── IRibbonHost dispatch ──────────────────────────────────────────

    def handle_ribbon_command(self, command_id: str) -> None:
        """Dispatch a command id to the matching page method.

        Unknown commands are silently ignored — the ribbon registry may
        ship buttons a page does not yet implement.
        """
        handler = self._ribbon_commands().get(command_id)
        if handler is None:
            return
        handler()

    # ── Notify the active RibbonBar ───────────────────────────────────

    def _notify_ribbon_state_changed(self) -> None:
        """Walk the parent chain looking for a ``_ribbon_bar`` attribute
        and ask it to re-pull this host's state. Safe no-op if the
        ribbon bar is not reachable (e.g. page hosted outside MainWindow
        in a smoke test).
        """
        # ``self`` is almost always a QWidget when this mixin is used;
        # be defensive about the narrowing for non-widget hosts.
        widget = self if isinstance(self, QWidget) else None
        if widget is None:
            return
        parent = widget.parentWidget()
        while parent is not None:
            bar = getattr(parent, "_ribbon_bar", None)
            if bar is not None and hasattr(bar, "refresh_active_state"):
                bar.refresh_active_state()
                return
            parent = parent.parentWidget()

    def _notify_ribbon_context_changed(self) -> None:
        """Ask the shell to recompute the active ribbon surface and state.

        Use this when the host's visible ribbon context may have changed,
        for example after a tab switch, selection change, or status
        transition that should swap to a different surface key.
        """
        widget = self if isinstance(self, QWidget) else None
        if widget is None:
            return
        parent = widget.parentWidget()
        while parent is not None:
            refresh_context = getattr(parent, "refresh_current_ribbon_context", None)
            if callable(refresh_context):
                refresh_context()
                return
            parent = parent.parentWidget()
        self._notify_ribbon_state_changed()
