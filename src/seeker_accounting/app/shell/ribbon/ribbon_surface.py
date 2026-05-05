"""RibbonSurface — adaptive command surface backed by the shared CommandBar.

Renders a :class:`RibbonSurfaceDef` (sequence of :class:`RibbonButtonDef` /
:class:`RibbonDividerDef`) through the shared adaptive
:class:`~seeker_accounting.shared.ui.components.command_bar.CommandBar`,
so labels never truncate and overflow is handled automatically when
horizontal space is tight.

The public API of this class is preserved verbatim: ``surface_key``,
``set_enablement``, ``reset_enablement_to_defaults``, ``refresh_icons``,
and the ``command_activated(str)`` signal — :class:`RibbonBar` and the
ribbon dispatcher continue to drive the same flow.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from seeker_accounting.app.shell.ribbon.ribbon_models import (
    RibbonButtonDef,
    RibbonDividerDef,
    RibbonSurfaceDef,
)
from seeker_accounting.shared.ui.components.command_bar import (
    CommandBar,
    CommandItem,
)
from seeker_accounting.shared.ui.icon_provider import IconProvider


class RibbonSurface(QWidget):
    """
    Adaptive horizontal strip of ribbon commands.

    One surface per :class:`RibbonSurfaceDef`, cached by :class:`RibbonBar`
    and shown/hidden as navigation context changes. Internally delegates
    rendering and overflow handling to a :class:`CommandBar` so that
    labels never truncate at narrow widths.
    """

    command_activated = Signal(str)

    def __init__(
        self,
        definition: RibbonSurfaceDef,
        icon_provider: IconProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonSurface")
        self._definition = definition
        self._items_by_id: dict[str, CommandItem] = {}

        items = self._build_command_items(definition)
        self._command_bar = CommandBar(
            items,
            icon_provider=icon_provider,
            parent=self,
        )
        self._command_bar.command_activated.connect(self.command_activated.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)
        layout.addWidget(self._command_bar, 1)

    # ── Public API ────────────────────────────────────────────────────

    @property
    def surface_key(self) -> str:
        return self._definition.surface_key

    def set_enablement(self, state: Mapping[str, bool]) -> None:
        """Apply host-provided enable map. Missing keys retain prior state."""
        self._command_bar.set_enablement(state)

    def reset_enablement_to_defaults(self) -> None:
        defaults: dict[str, bool] = {
            item.command_id: item.default_enabled
            for item in self._definition.items
            if isinstance(item, RibbonButtonDef)
        }
        self._command_bar.set_enablement(defaults)

    def refresh_icons(self) -> None:
        self._command_bar.refresh_icons()

    # ── Internals ─────────────────────────────────────────────────────

    def _build_command_items(
        self, definition: RibbonSurfaceDef
    ) -> list[CommandItem]:
        """Translate ribbon definition items into :class:`CommandItem`s.

        Each :class:`RibbonDividerDef` advances the group key, which causes
        the underlying :class:`CommandBar` to draw a group separator
        between the surrounding command groups.
        """
        items: list[CommandItem] = []
        group_index = 0
        current_group = f"g{group_index}"

        for entry in definition.items:
            if isinstance(entry, RibbonDividerDef):
                group_index += 1
                current_group = f"g{group_index}"
                continue
            if isinstance(entry, RibbonButtonDef):
                priority = "primary" if entry.variant == "primary" else "secondary"
                cmd = CommandItem(
                    command_id=entry.command_id,
                    label=entry.label,
                    icon_name=entry.icon_name,
                    tooltip=entry.tooltip,
                    variant=entry.variant,
                    priority=priority,
                    enabled=entry.default_enabled,
                    group=current_group,
                )
                items.append(cmd)
                self._items_by_id[entry.command_id] = cmd
        return items
