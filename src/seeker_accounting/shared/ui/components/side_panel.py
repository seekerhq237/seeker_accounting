"""SidePanel — non-modal contextual panel for issue resolution / context.

Used to replace modal-on-modal patterns: when a primary form needs to
launch a secondary step, the panel slides in beside the form rather
than popping a second dialog.

The panel has no business logic: callers feed it a content widget,
title, optional severity, and connect to the ``closed`` signal. The
panel can be docked either to the right of a parent layout or used
free-standing (e.g. inside a ``QSplitter``).
"""
from __future__ import annotations

from typing import Final

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


class SidePanel(QFrame):
    """A right-aligned non-modal panel suitable for contextual workflows."""

    closed = Signal()

    def __init__(
        self,
        title: str = "",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SidePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sizes = DEFAULT_TOKENS.sizes
        spacing = DEFAULT_TOKENS.spacing
        self.setMinimumWidth(sizes.side_panel_min_width)
        self.setMaximumWidth(sizes.side_panel_max_width)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header row.
        header = QFrame(self)
        header.setObjectName("SidePanelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            sizes.side_panel_padding,
            spacing.compact_gap,
            spacing.compact_gap,
            spacing.compact_gap,
        )
        header_layout.setSpacing(spacing.compact_gap)
        self._title_label = QLabel(title, header)
        self._title_label.setObjectName("SidePanelTitle")
        header_layout.addWidget(self._title_label, 1)
        self._close_btn = QPushButton("×", header)
        self._close_btn.setObjectName("SidePanelCloseButton")
        self._close_btn.setFlat(True)
        self._close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.clicked.connect(self._on_close)
        header_layout.addWidget(self._close_btn)
        outer.addWidget(header)

        # Body.
        self._body_host = QFrame(self)
        self._body_host.setObjectName("SidePanelBody")
        self._body_layout = QStackedLayout(self._body_host)
        self._body_layout.setContentsMargins(
            sizes.side_panel_padding,
            sizes.side_panel_padding,
            sizes.side_panel_padding,
            sizes.side_panel_padding,
        )
        outer.addWidget(self._body_host, 1)

        self._content: QWidget | None = None

    # ── public API -----------------------------------------------------

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def set_content(self, widget: QWidget) -> None:
        if self._content is not None:
            self._body_layout.removeWidget(self._content)
            self._content.setParent(None)
            self._content.deleteLater()
        self._content = widget
        self._body_layout.addWidget(widget)
        self._body_layout.setCurrentWidget(widget)

    def clear(self) -> None:
        if self._content is not None:
            self._body_layout.removeWidget(self._content)
            self._content.setParent(None)
            self._content.deleteLater()
            self._content = None

    def _on_close(self) -> None:
        self.closed.emit()
        self.hide()
