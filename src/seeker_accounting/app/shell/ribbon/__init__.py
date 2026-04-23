"""
Ribbon shell subsystem.

Sage-style single context-aware ribbon band (no tabs). Contents swap in/out
based on the active navigation target, and optionally based on the focused
child window. Pages and child windows that want to receive ribbon clicks
implement :class:`IRibbonHost`.

Architecture (UI-only — no service or repository changes):

    RibbonBar (QFrame hosted in MainWindow between menu bar and workspace)
      └── active RibbonSurface (QWidget)
            └── RibbonButton / RibbonDivider widgets

    ribbon_registry   — catalogue: nav_id / child_window_key → list of items
    IRibbonHost       — protocol: active page/window handles command_id
    RibbonActionDispatcher — routes command_id → host | navigation | palette
"""

from seeker_accounting.app.shell.ribbon.ribbon_actions import RibbonActionDispatcher
from seeker_accounting.app.shell.ribbon.ribbon_bar import RibbonBar
from seeker_accounting.app.shell.ribbon.ribbon_button import RibbonButton
from seeker_accounting.app.shell.ribbon.ribbon_host import IRibbonHost
from seeker_accounting.app.shell.ribbon.ribbon_models import (
    RibbonButtonDef,
    RibbonDividerDef,
    RibbonItemDef,
    RibbonSurfaceDef,
)
from seeker_accounting.app.shell.ribbon.ribbon_host_mixin import RibbonHostMixin
from seeker_accounting.app.shell.ribbon.ribbon_registry import RibbonRegistry
from seeker_accounting.app.shell.ribbon.ribbon_surface import RibbonSurface

__all__ = [
    "IRibbonHost",
    "RibbonActionDispatcher",
    "RibbonBar",
    "RibbonButton",
    "RibbonButtonDef",
    "RibbonDividerDef",
    "RibbonHostMixin",
    "RibbonItemDef",
    "RibbonRegistry",
    "RibbonSurface",
    "RibbonSurfaceDef",
]
