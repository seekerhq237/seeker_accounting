"""
RibbonActionDispatcher — routes ribbon command_id → active host.

Kept as a tiny, explicit class so it can later be extended to handle
global commands (e.g. ``app.open_command_palette``) without touching
the ribbon bar or hosts.
"""

from __future__ import annotations

from seeker_accounting.app.shell.ribbon.ribbon_host import IRibbonHost


class RibbonActionDispatcher:
    """Dispatches ribbon commands to the currently-active host."""

    def __init__(self) -> None:
        self._active_host: IRibbonHost | None = None

    def set_active_host(self, host: IRibbonHost | None) -> None:
        self._active_host = host

    def dispatch(self, command_id: str) -> None:
        host = self._active_host
        if host is None:
            return
        try:
            host.handle_ribbon_command(command_id)
        except NotImplementedError:
            # Host declines — silent no-op keeps the shell stable.
            return
