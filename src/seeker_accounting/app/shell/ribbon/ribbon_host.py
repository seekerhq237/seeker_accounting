"""
IRibbonHost protocol.

Pages and child windows that want to receive ribbon clicks implement this
protocol. The ribbon bar asks the active host for per-command enablement
and forwards command-id clicks to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class IRibbonHost(Protocol):
    """
    Minimal contract between the ribbon and its active host.

    ``handle_ribbon_command`` receives the opaque command id defined by
    the ribbon surface in :mod:`ribbon_registry`. Hosts should treat any
    unknown command id as a no-op (return without raising) so the shell
    can continue to operate even if a button's wiring is missing.

    ``ribbon_state`` returns a mapping from command id to *enabled* flag.
    Missing keys fall back to the button's ``default_enabled`` value.
    """

    def handle_ribbon_command(self, command_id: str) -> None: ...

    def ribbon_state(self) -> Mapping[str, bool]: ...
