"""RibbonSurface — renders a sequence of ribbon items for one context."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

from seeker_accounting.app.shell.ribbon.ribbon_button import RibbonButton
from seeker_accounting.app.shell.ribbon.ribbon_models import (
    RibbonButtonDef,
    RibbonDividerDef,
    RibbonSurfaceDef,
)
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


class RibbonSurface(QWidget):
    """
    Flat horizontal strip of ribbon buttons and dividers.

    Surfaces are built once per ``RibbonSurfaceDef`` and cached by the
    :class:`RibbonBar`. They are show/hidden as navigation context changes.
    Commands are emitted via :attr:`command_activated`; callers decide where
    to dispatch them.
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
        self._buttons: dict[str, RibbonButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for item in definition.items:
            if isinstance(item, RibbonButtonDef):
                button = RibbonButton(item, icon_provider, self._emit_command, self)
                layout.addWidget(button)
                self._buttons[item.command_id] = button
            elif isinstance(item, RibbonDividerDef):
                layout.addWidget(self._make_divider())

        layout.addStretch(1)

    # ── Public API ────────────────────────────────────────────────────

    @property
    def surface_key(self) -> str:
        return self._definition.surface_key

    def set_enablement(self, state: Mapping[str, bool]) -> None:
        """Apply host-provided enable map. Missing keys retain defaults."""
        for cmd_id, button in self._buttons.items():
            if cmd_id in state:
                button.setEnabled(bool(state[cmd_id]))

    def reset_enablement_to_defaults(self) -> None:
        for item in self._definition.items:
            if isinstance(item, RibbonButtonDef):
                self._buttons[item.command_id].setEnabled(item.default_enabled)

    def refresh_icons(self) -> None:
        for button in self._buttons.values():
            button.refresh_icon()

    # ── Internals ─────────────────────────────────────────────────────

    def _emit_command(self, command_id: str) -> None:
        self.command_activated.emit(command_id)

    def _make_divider(self) -> QFrame:
        divider = QFrame(self)
        divider.setObjectName("RibbonDivider")
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Plain)
        divider.setFixedWidth(1)
        divider.setFixedHeight(DEFAULT_TOKENS.sizes.ribbon_divider_height)
        return divider
