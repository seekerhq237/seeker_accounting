"""Document workstation skeleton (Operational Desktop Phase 3).

Composable 5-zone primitive for document entry and detail screens:

    1. Command row           (top)
    2. Document identity     (doc type / number / status / counterparty)
    3. Metadata block        (aligned 2-column grid of header fields)
    4. Lines area + totals   (dominant body; totals docked right)
    5. Action rail           (bottom: Save / Post / Cancel / Close)

Hosts inject their own widgets into each zone — the primitive only
establishes the operational grammar (object names, flat framing,
proportions). It owns no business logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass(slots=True)
class DocumentWorkspaceSpec:
    """Static configuration for a document workspace instance."""

    document_type_label: str = ""
    show_identity_strip: bool = True
    show_metadata_strip: bool = True
    show_totals_dock: bool = True
    show_command_row: bool = True
    show_action_rail: bool = True
    # Column count for the metadata grid (label + value pairs).
    metadata_columns: int = 2
    metadata_label_width: int = 92


class DocumentWorkspace(QFrame):
    """Container that renders the five operational zones of a document.

    All zones are exposed as public-read widgets so host screens can
    add their own controls. Zones not requested by the spec remain
    hidden; the layout collapses around them.
    """

    def __init__(
        self,
        spec: Optional[DocumentWorkspaceSpec] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._spec = spec or DocumentWorkspaceSpec()
        self.setObjectName("DocumentWorkspace")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 1. Command row
        self._command_row = self._build_strip("DocumentCommandRow")
        outer.addWidget(self._command_row)
        self._command_row.setVisible(self._spec.show_command_row)

        # 2. Identity strip
        self._identity_strip = self._build_identity_strip()
        outer.addWidget(self._identity_strip)
        self._identity_strip.setVisible(self._spec.show_identity_strip)

        # 3. Metadata strip
        self._metadata_strip, self._metadata_grid = self._build_metadata_strip()
        outer.addWidget(self._metadata_strip)
        self._metadata_strip.setVisible(self._spec.show_metadata_strip)

        # 4. Body: lines + totals dock
        body = QFrame(self)
        body.setObjectName("DocumentBody")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._lines_host = QFrame(body)
        self._lines_host.setObjectName("DocumentLinesHost")
        self._lines_host_layout = QVBoxLayout(self._lines_host)
        self._lines_host_layout.setContentsMargins(0, 0, 0, 0)
        self._lines_host_layout.setSpacing(0)
        body_layout.addWidget(self._lines_host, 1)

        self._totals_dock = QFrame(body)
        self._totals_dock.setObjectName("TotalsDock")
        self._totals_dock_layout = QVBoxLayout(self._totals_dock)
        self._totals_dock_layout.setContentsMargins(12, 10, 12, 10)
        self._totals_dock_layout.setSpacing(6)
        body_layout.addWidget(self._totals_dock, 0)
        self._totals_dock.setVisible(self._spec.show_totals_dock)

        outer.addWidget(body, 1)

        # 5. Action rail
        self._action_rail = self._build_strip("ActionRail")
        self._action_rail.setMinimumHeight(44)
        outer.addWidget(self._action_rail)
        self._action_rail.setVisible(self._spec.show_action_rail)

    # ── Zone accessors ────────────────────────────────────────────────

    @property
    def command_row(self) -> QFrame:
        return self._command_row

    @property
    def identity_strip(self) -> QFrame:
        return self._identity_strip

    @property
    def metadata_strip(self) -> QFrame:
        return self._metadata_strip

    @property
    def metadata_grid(self) -> QGridLayout:
        return self._metadata_grid

    @property
    def lines_host(self) -> QFrame:
        return self._lines_host

    @property
    def totals_dock(self) -> QFrame:
        return self._totals_dock

    @property
    def action_rail(self) -> QFrame:
        return self._action_rail

    # ── Helpers host screens call when building layouts ──────────────

    def set_lines_widget(self, widget: QWidget) -> None:
        """Replace the lines-host contents with a single widget (e.g. a grid)."""
        while self._lines_host_layout.count():
            item = self._lines_host_layout.takeAt(0)
            if item is None:
                continue
            child = item.widget()
            if child is not None:
                child.setParent(None)
        self._lines_host_layout.addWidget(widget)

    def add_metadata_pair(self, row: int, label: str, value_widget: QWidget) -> None:
        """Add a (MetaLabel, value) pair at the given grid row."""
        lbl = QLabel(label, self._metadata_strip)
        lbl.setObjectName("MetaLabel")
        column_count = max(self._spec.metadata_columns, 1)
        grid_row = row // column_count
        pair_index = row % column_count
        label_col = pair_index * 2
        value_col = label_col + 1
        self._metadata_grid.addWidget(
            lbl,
            grid_row,
            label_col,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._metadata_grid.addWidget(value_widget, grid_row, value_col)

    def add_metadata_full_row(self, row: int, label: str, value_widget: QWidget) -> None:
        """Add a label/value pair whose value spans the full metadata width."""
        lbl = QLabel(label, self._metadata_strip)
        lbl.setObjectName("MetaLabel")
        grid_row = row // max(self._spec.metadata_columns, 1)
        self._metadata_grid.addWidget(
            lbl,
            grid_row,
            0,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        span = max((self._spec.metadata_columns * 2) - 1, 1)
        self._metadata_grid.addWidget(value_widget, grid_row, 1, 1, span)

    def set_identity(
        self,
        document_label: str,
        document_number: str = "",
        status_widget: QWidget | None = None,
        dates_text: str = "",
        counterparty: str = "",
    ) -> None:
        self._identity_doc_label.setText(document_label or "")
        self._identity_number_label.setText(document_number or "")
        self._identity_dates_label.setText(dates_text or "")
        self._identity_counterparty_label.setText(counterparty or "")

        # Replace the status slot content.
        if self._identity_status_host_layout.count():
            item = self._identity_status_host_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setParent(None)
        if status_widget is not None:
            self._identity_status_host_layout.addWidget(status_widget)

    # ── Builders ──────────────────────────────────────────────────────

    def _build_strip(self, object_name: str) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName(object_name)
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        return frame

    def _build_identity_strip(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("DocumentIdentityStrip")
        frame.setFrameShape(QFrame.Shape.NoFrame)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self._identity_doc_label = QLabel(self._spec.document_type_label, frame)
        self._identity_doc_label.setObjectName("PanelHeaderTitle")

        self._identity_number_label = QLabel("", frame)
        self._identity_number_label.setObjectName("MetaValue")

        self._identity_status_host = QWidget(frame)
        self._identity_status_host_layout = QHBoxLayout(self._identity_status_host)
        self._identity_status_host_layout.setContentsMargins(0, 0, 0, 0)
        self._identity_status_host_layout.setSpacing(0)

        self._identity_dates_label = QLabel("", frame)
        self._identity_dates_label.setObjectName("MetaValue")

        self._identity_counterparty_label = QLabel("", frame)
        self._identity_counterparty_label.setObjectName("MetaValue")

        layout.addWidget(self._identity_doc_label, 0)
        layout.addWidget(self._identity_number_label, 0)
        layout.addWidget(self._identity_status_host, 0)
        layout.addWidget(self._identity_dates_label, 0)
        layout.addStretch(1)
        layout.addWidget(self._identity_counterparty_label, 0)
        return frame

    def _build_metadata_strip(self) -> tuple[QFrame, QGridLayout]:
        frame = QFrame(self)
        frame.setObjectName("MetaStrip")
        frame.setFrameShape(QFrame.Shape.NoFrame)
        grid = QGridLayout(frame)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for pair_index in range(max(self._spec.metadata_columns, 1)):
            label_col = pair_index * 2
            value_col = label_col + 1
            grid.setColumnMinimumWidth(label_col, self._spec.metadata_label_width)
            grid.setColumnStretch(label_col, 0)
            grid.setColumnStretch(value_col, 1)
        return frame, grid
