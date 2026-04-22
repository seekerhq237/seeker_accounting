"""Operational Desktop RegisterPage primitive (Phase 4).

Layout skeleton for register/list screens:

    ┌─ ToolbarStrip ─────────────────────────────┐
    │ search · filters · record-count · refresh │
    ├─ ActionBand ───────────────────────────────┤
    │ New / Edit / Post / Cancel / Print / …    │
    ├─ Table                                    │
    │ (dense, full-bleed; no card wrapper)      │
    │                                           │
    └───────────────────────────────────────────┘

Host screens populate three public zones (`toolbar_strip`,
`action_band`, `table_host`). Empty / no-company states are
rendered by host screens via the existing QStackedWidget patterns —
this primitive owns layout grammar only.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class RegisterPage(QWidget):
    """Flat register skeleton. Hosts inject toolbar, actions, and table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RegisterPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toolbar strip (filters, search, record count).
        self._toolbar_strip = QFrame(self)
        self._toolbar_strip.setObjectName("ToolbarStrip")
        self._toolbar_strip.setFrameShape(QFrame.Shape.NoFrame)
        self._toolbar_strip_layout = QHBoxLayout(self._toolbar_strip)
        self._toolbar_strip_layout.setContentsMargins(8, 2, 8, 2)
        self._toolbar_strip_layout.setSpacing(6)
        root.addWidget(self._toolbar_strip)

        # Action band (primary/secondary/ghost action buttons).
        self._action_band = QFrame(self)
        self._action_band.setObjectName("ActionBand")
        self._action_band.setFrameShape(QFrame.Shape.NoFrame)
        self._action_band_layout = QHBoxLayout(self._action_band)
        self._action_band_layout.setContentsMargins(8, 2, 8, 2)
        self._action_band_layout.setSpacing(4)
        root.addWidget(self._action_band)

        # Table host: holds either the main table or a stacked empty-state view.
        self._table_host = QWidget(self)
        self._table_host.setObjectName("RegisterTableHost")
        self._table_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table_host_layout = QVBoxLayout(self._table_host)
        self._table_host_layout.setContentsMargins(0, 0, 0, 0)
        self._table_host_layout.setSpacing(0)
        root.addWidget(self._table_host, 1)

    # ── Zone accessors ────────────────────────────────────────────────

    @property
    def toolbar_strip(self) -> QFrame:
        return self._toolbar_strip

    @property
    def toolbar_strip_layout(self) -> QHBoxLayout:
        return self._toolbar_strip_layout

    @property
    def action_band(self) -> QFrame:
        return self._action_band

    @property
    def action_band_layout(self) -> QHBoxLayout:
        return self._action_band_layout

    @property
    def table_host(self) -> QWidget:
        return self._table_host

    def set_table_widget(self, widget: QWidget) -> None:
        """Replace the table host's contents with a single widget.

        Accepts a QTableWidget directly, or a QStackedWidget when the
        host wants to swap between empty-state / no-company / table.
        """
        while self._table_host_layout.count():
            item = self._table_host_layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._table_host_layout.addWidget(widget)
