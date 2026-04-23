"""
Ribbon item definitions.

Immutable, hashable dataclasses that describe the contents of a ribbon
surface. These are consumed by :class:`RibbonSurface` to render widgets,
and by :class:`RibbonRegistry` to catalogue ribbon surfaces per navigation
context and per child-window kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union


RibbonButtonVariant = Literal["default", "primary", "danger"]


@dataclass(frozen=True, slots=True)
class RibbonButtonDef:
    """
    A single clickable ribbon button (large icon-above-label).

    ``command_id`` is the opaque string handed to the active host via
    :meth:`IRibbonHost.handle_ribbon_command`. Hosts should treat unknown
    command ids as a no-op rather than raising.
    """

    command_id: str
    label: str
    icon_name: str
    tooltip: str = ""
    variant: RibbonButtonVariant = "default"
    default_enabled: bool = True


@dataclass(frozen=True, slots=True)
class RibbonDividerDef:
    """Thin vertical divider between logical ribbon groups."""

    key: str = "divider"


RibbonItemDef = Union[RibbonButtonDef, RibbonDividerDef]


@dataclass(frozen=True, slots=True)
class RibbonSurfaceDef:
    """
    A full ribbon surface catalogue entry.

    One surface maps to one navigation context (for register pages) or
    one child-window kind (for top-level document windows).
    """

    surface_key: str
    items: tuple[RibbonItemDef, ...] = field(default_factory=tuple)
