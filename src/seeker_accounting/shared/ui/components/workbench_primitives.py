"""EmptyState, KpiTile, WorkbenchHeader — workbench-grade primitives.

These are leaf UI primitives — no business logic, no service imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

# ──────────────────────────────────────────────────────────────────────
# EmptyState
# ──────────────────────────────────────────────────────────────────────


class EmptyState(QFrame):
    """Empty-state block: glyph (text), headline, body, optional actions.

    Use one per surface; keep copy intentional ("3 employees missing
    CNPS number" is not an empty state).
    """

    primary_clicked = Signal()
    secondary_clicked = Signal()

    def __init__(
        self,
        *,
        headline: str,
        body: str = "",
        primary_label: str | None = None,
        secondary_label: str | None = None,
        glyph: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        sizes = DEFAULT_TOKENS.sizes
        spacing = DEFAULT_TOKENS.spacing

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
        )
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setSpacing(spacing.compact_gap)

        inner = QFrame(self)
        inner.setMaximumWidth(sizes.empty_state_max_width)
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        inner_layout.setSpacing(spacing.compact_gap)

        if glyph:
            glyph_label = QLabel(glyph, inner)
            glyph_label.setObjectName("EmptyStateGlyph")
            glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner_layout.addWidget(glyph_label)

        head = QLabel(headline, inner)
        head.setObjectName("EmptyStateHeadline")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setWordWrap(True)
        inner_layout.addWidget(head)

        if body:
            body_label = QLabel(body, inner)
            body_label.setObjectName("EmptyStateBody")
            body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body_label.setWordWrap(True)
            inner_layout.addWidget(body_label)

        if primary_label or secondary_label:
            actions = QHBoxLayout()
            actions.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            actions.setSpacing(sizes.empty_state_action_gap)
            if secondary_label:
                btn = QPushButton(secondary_label, inner)
                btn.setObjectName("EmptyStateSecondaryButton")
                btn.clicked.connect(self.secondary_clicked.emit)
                actions.addWidget(btn)
            if primary_label:
                btn = QPushButton(primary_label, inner)
                btn.setObjectName("EmptyStatePrimaryButton")
                btn.setDefault(True)
                btn.clicked.connect(self.primary_clicked.emit)
                actions.addWidget(btn)
            inner_layout.addSpacing(spacing.compact_gap)
            inner_layout.addLayout(actions)

        outer.addWidget(inner, 0, Qt.AlignmentFlag.AlignCenter)


# ──────────────────────────────────────────────────────────────────────
# KpiTile
# ──────────────────────────────────────────────────────────────────────


Trend = Literal["up", "down", "flat", "none"]


@dataclass(frozen=True, slots=True)
class KpiTileData:
    label: str
    value: str
    trend: Trend = "none"
    trend_label: str = ""
    drilldown_id: str | None = None


class KpiTile(QFrame):
    """Single KPI tile: small label, large value, optional trend + drilldown."""

    clicked = Signal(str)  # emits drilldown_id

    def __init__(self, data: KpiTileData, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("KpiTile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._data = data

        sizes = DEFAULT_TOKENS.sizes
        spacing = DEFAULT_TOKENS.spacing
        self.setMinimumWidth(sizes.kpi_tile_min_width)
        self.setMinimumHeight(sizes.kpi_tile_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        clickable = data.drilldown_id is not None
        self.setProperty("clickable", "true" if clickable else "false")
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            sizes.kpi_tile_padding_h,
            sizes.kpi_tile_padding_v,
            sizes.kpi_tile_padding_h,
            sizes.kpi_tile_padding_v,
        )
        layout.setSpacing(spacing.dialog_label_gap)

        self._label_label = QLabel(data.label, self)
        self._label_label.setObjectName("KpiTileLabel")
        layout.addWidget(self._label_label)

        self._value_label = QLabel(data.value, self)
        self._value_label.setObjectName("KpiTileValue")
        layout.addWidget(self._value_label)

        self._trend_label = QLabel("", self)
        self._trend_label.setObjectName(self._trend_object_name(data.trend))
        if data.trend != "none":
            arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(data.trend, "")
            self._trend_label.setText(f"{arrow} {data.trend_label}".strip())
        else:
            self._trend_label.setVisible(False)
        layout.addWidget(self._trend_label)

    @staticmethod
    def _trend_object_name(trend: Trend) -> str:
        return {
            "up": "KpiTileTrendUp",
            "down": "KpiTileTrendDown",
            "flat": "KpiTileTrendFlat",
        }.get(trend, "KpiTileTrendFlat")

    def update_data(self, data: KpiTileData) -> None:
        self._data = data
        self._label_label.setText(data.label)
        self._value_label.setText(data.value)
        if data.trend == "none":
            self._trend_label.setVisible(False)
        else:
            arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(data.trend, "")
            self._trend_label.setText(f"{arrow} {data.trend_label}".strip())
            self._trend_label.setObjectName(self._trend_object_name(data.trend))
            self._trend_label.setVisible(True)

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        if self._data.drilldown_id:
            self.clicked.emit(self._data.drilldown_id)
        super().mousePressEvent(event)  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────
# WorkbenchHeader
# ──────────────────────────────────────────────────────────────────────


class WorkbenchHeader(QFrame):
    """Top-of-workbench title strip with breadcrumb + slot for context controls.

    Layout::

        ┌──────────────────────────────────────────────────────────────┐
        │ Breadcrumb                                                   │
        │ Title              Subtitle              [context slot]      │
        └──────────────────────────────────────────────────────────────┘

    Callers populate the right-hand context slot with whatever suits
    (period picker, primary action, status chip, etc.) via
    :meth:`set_context_widget`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkbenchHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sizes = DEFAULT_TOKENS.sizes
        self.setMinimumHeight(sizes.workbench_header_height)
        self.setMaximumHeight(sizes.workbench_header_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            sizes.workbench_header_padding_h, 6, sizes.workbench_header_padding_h, 6
        )
        outer.setSpacing(2)

        self._breadcrumb = QLabel("", self)
        self._breadcrumb.setObjectName("WorkbenchHeaderBreadcrumb")
        self._breadcrumb.setVisible(False)
        outer.addWidget(self._breadcrumb)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._title = QLabel("", self)
        self._title.setObjectName("WorkbenchHeaderTitle")
        row.addWidget(self._title)

        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("WorkbenchHeaderSubtitle")
        row.addWidget(self._subtitle)

        row.addStretch(1)

        self._context_host = QFrame(self)
        self._context_host.setObjectName("WorkbenchHeaderContextHost")
        self._context_layout = QHBoxLayout(self._context_host)
        self._context_layout.setContentsMargins(0, 0, 0, 0)
        self._context_layout.setSpacing(8)
        row.addWidget(self._context_host)

        outer.addLayout(row)

    # ── public API -----------------------------------------------------

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle.setText(subtitle)

    def set_breadcrumb(self, crumb: str) -> None:
        self._breadcrumb.setText(crumb)
        self._breadcrumb.setVisible(bool(crumb))

    def set_context_widget(self, widget: QWidget | None) -> None:
        # Clear existing.
        while self._context_layout.count():
            item = self._context_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if widget is not None:
            self._context_layout.addWidget(widget)

    def add_context_widget(self, widget: QWidget) -> None:
        self._context_layout.addWidget(widget)
