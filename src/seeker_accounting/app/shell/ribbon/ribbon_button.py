"""RibbonButton — icon-above-label flat tool button used in RibbonSurface."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QToolButton, QWidget

from seeker_accounting.app.shell.ribbon.ribbon_models import RibbonButtonDef
from seeker_accounting.shared.ui.icon_provider import IconProvider
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


class RibbonButton(QToolButton):
    """
    Large icon-above-label ribbon button.

    Width is fixed via the ``ribbon_button_width`` token; height stretches
    to the ribbon surface height. Icon size is driven by
    ``ribbon_button_icon_size``. Clicks are delivered as the button's own
    ``command_id`` via *on_click*.
    """

    def __init__(
        self,
        definition: RibbonButtonDef,
        icon_provider: IconProvider,
        on_click: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._definition = definition
        self._icon_provider = icon_provider
        self._on_click = on_click

        sizes = DEFAULT_TOKENS.sizes
        self.setObjectName("RibbonButton")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setText(definition.label)
        self.setToolTip(definition.tooltip or definition.label)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setFixedWidth(sizes.ribbon_button_width)
        self.setIconSize(QSize(sizes.ribbon_button_icon_size, sizes.ribbon_button_icon_size))
        self._apply_icon()

        # Visual variants consumed by QSS via dynamic properties.
        self.setProperty("ribbonVariant", definition.variant)
        self.setProperty("commandId", definition.command_id)

        self.setEnabled(definition.default_enabled)
        self.clicked.connect(self._handle_clicked)

    # ── Public API ────────────────────────────────────────────────────

    @property
    def command_id(self) -> str:
        return self._definition.command_id

    def refresh_icon(self) -> None:
        """Re-apply icon after a theme change."""
        self._apply_icon()

    # ── Internals ─────────────────────────────────────────────────────

    def _apply_icon(self) -> None:
        size = DEFAULT_TOKENS.sizes.ribbon_button_icon_size
        self.setIcon(self._icon_provider.icon(self._definition.icon_name, size=size))

    def _handle_clicked(self) -> None:
        if not self.isEnabled():
            return
        self._on_click(self._definition.command_id)
