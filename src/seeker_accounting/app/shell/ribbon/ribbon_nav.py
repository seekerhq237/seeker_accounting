"""
Ribbon navigation helpers — produce handler/state entries for the
``Related`` group that every accounting ribbon surface exposes.

Pages participating in :data:`RELATED_PAGES` call these helpers from
their ``_ribbon_commands()`` and ``ribbon_state()`` implementations so
the goto shortcut wiring stays in one place.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from seeker_accounting.app.shell.ribbon.ribbon_registry import (
    RELATED_PAGES,
    related_goto_command_id,
)


def related_goto_handlers(
    service_registry: Any,
    surface_key: str,
) -> Mapping[str, Callable[[], None]]:
    """Return ``{command_id: handler}`` for the surface's related-page shortcuts."""
    spec = RELATED_PAGES.get(surface_key)
    if not spec:
        return {}
    nav = service_registry.navigation_service
    handlers: dict[str, Callable[[], None]] = {}
    for target_nav_id, _label, _icon in spec:
        command_id = related_goto_command_id(surface_key, target_nav_id)
        handlers[command_id] = (lambda nid=target_nav_id: nav.navigate(nid))
    return handlers


def related_goto_state(surface_key: str) -> Mapping[str, bool]:
    """Return ``{command_id: True}`` for every goto shortcut on the surface."""
    spec = RELATED_PAGES.get(surface_key)
    if not spec:
        return {}
    return {
        related_goto_command_id(surface_key, target_nav_id): True
        for target_nav_id, _label, _icon in spec
    }
