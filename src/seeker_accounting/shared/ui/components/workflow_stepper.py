"""WorkflowStepper — horizontal multi-stage workflow indicator.

A generic, business-domain-agnostic stepper widget that renders a row of
steps with an indicator (number/check/slash/!) and a label, connected by
horizontal lines. Visual styling for the container frame is driven by
QSS via the ``#WorkflowStepper`` selector; indicators, connectors and
glyphs are painted manually using the active theme palette.

The component is a pure UI primitive — it must not import from ``app/``
or ``modules/`` and contains no business logic.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from seeker_accounting.shared.ui.styles.palette import ThemePalette, get_palette
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

WorkflowStepState = Literal["pending", "active", "complete", "blocked", "skipped"]


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    """A single stage in a :class:`WorkflowStepper`."""

    key: str
    label: str
    description: str = ""
    state: WorkflowStepState = "pending"
    badge: str = ""
    enabled: bool = True


def _active_palette() -> ThemePalette:
    """Best-effort lookup of the currently active :class:`ThemePalette`.

    Mirrors the helper in :mod:`status_chip` — duplicated locally so the
    two components remain independent leaf widgets.
    """
    app = QApplication.instance()
    if app is not None:
        try:
            window = app.palette().color(app.palette().ColorRole.Window)
            if window.lightness() < 128:
                return get_palette("dark")
        except Exception:
            pass
    return get_palette("light")


class WorkflowStepper(QWidget):
    """Horizontal stepper widget surfacing a multi-stage workflow."""

    step_clicked = Signal(str)

    def __init__(
        self,
        steps: Sequence[WorkflowStep] = (),
        *,
        clickable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WorkflowStepper")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        sizes = DEFAULT_TOKENS.sizes
        self.setFixedHeight(sizes.workflow_stepper_height)
        self.setMouseTracking(True)

        self._clickable: bool = bool(clickable)
        self._steps: list[WorkflowStep] = list(steps)
        self._hover_index: int | None = None
        # Cached per-step geometry: (cx, cy, hit_rect).
        self._geom: list[tuple[int, int, QRect]] = []

    # ── public API ────────────────────────────────────────────────────

    def steps(self) -> tuple[WorkflowStep, ...]:
        return tuple(self._steps)

    def set_steps(self, steps: Sequence[WorkflowStep]) -> None:
        self._steps = list(steps)
        self._hover_index = None
        self._geom = []
        self.updateGeometry()
        self.update()

    def set_step_state(self, key: str, state: WorkflowStepState) -> None:
        for idx, step in enumerate(self._steps):
            if step.key == key:
                self._steps[idx] = replace(step, state=state)
                self.update()
                return

    def set_step_badge(self, key: str, badge: str) -> None:
        for idx, step in enumerate(self._steps):
            if step.key == key:
                self._steps[idx] = replace(step, badge=badge)
                self.update()
                return

    def set_active_step(self, key: str | None) -> None:
        if key is None:
            for idx, step in enumerate(self._steps):
                if step.state == "active":
                    self._steps[idx] = replace(step, state="pending")
            self.update()
            return

        target = -1
        for idx, step in enumerate(self._steps):
            if step.key == key:
                target = idx
                break
        if target < 0:
            return

        for idx, step in enumerate(self._steps):
            if step.state in ("blocked", "skipped"):
                continue
            if idx < target:
                if step.state in ("pending", "active"):
                    self._steps[idx] = replace(step, state="complete")
            elif idx == target:
                self._steps[idx] = replace(step, state="active")
            else:
                if step.state in ("complete", "active"):
                    self._steps[idx] = replace(step, state="pending")
        self.update()

    # ── sizing ────────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:
        sizes = DEFAULT_TOKENS.sizes
        n = max(1, len(self._steps))
        return QSize(
            n * sizes.workflow_stepper_step_min_width,
            sizes.workflow_stepper_height,
        )

    def minimumSizeHint(self) -> QSize:
        sizes = DEFAULT_TOKENS.sizes
        n = max(1, len(self._steps))
        return QSize(
            n * sizes.workflow_stepper_step_min_width,
            sizes.workflow_stepper_height,
        )

    # ── geometry cache ────────────────────────────────────────────────

    def _recompute_geometry(self) -> None:
        sizes = DEFAULT_TOKENS.sizes
        rect = self.rect()
        n = len(self._steps)
        self._geom = []
        if n == 0:
            return

        # Column width: divide width evenly across steps.
        col_w = max(sizes.workflow_stepper_step_min_width, rect.width() // n)
        cy = rect.center().y() - 6  # bias indicator slightly upward to leave room
        # Recompute cy based on actual layout: indicator center sits at top
        # third so label + description fit underneath.
        indicator_top_padding = 10
        cy = rect.top() + indicator_top_padding + sizes.workflow_stepper_dot_size // 2

        for i in range(n):
            left = rect.left() + i * (rect.width() // n)
            right = rect.left() + (i + 1) * (rect.width() // n)
            cx = (left + right) // 2
            hit_rect = QRect(left, rect.top(), right - left, rect.height())
            self._geom.append((cx, cy, hit_rect))

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._geom = []  # invalidate, recomputed lazily on next paint

    # ── mouse handling ────────────────────────────────────────────────

    def _index_at(self, pos: QPoint) -> int | None:
        if not self._geom:
            self._recompute_geometry()
        for idx, (_cx, _cy, hit) in enumerate(self._geom):
            if hit.contains(pos):
                return idx
        return None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if not self._clickable:
            self._hover_index = None
            super().mouseMoveEvent(event)
            return
        idx = self._index_at(event.position().toPoint())
        new_hover: int | None = None
        if idx is not None and 0 <= idx < len(self._steps):
            if self._steps[idx].enabled:
                new_hover = idx
        if new_hover != self._hover_index:
            self._hover_index = new_hover
            if new_hover is not None:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.unsetCursor()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        if self._hover_index is not None:
            self._hover_index = None
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._clickable:
            idx = self._index_at(event.position().toPoint())
            if idx is not None and 0 <= idx < len(self._steps):
                step = self._steps[idx]
                if step.enabled:
                    self.step_clicked.emit(step.key)
                    event.accept()
                    return
        super().mousePressEvent(event)

    # ── painting ──────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)  # styled background frame from QSS
        if not self._steps:
            return
        if not self._geom:
            self._recompute_geometry()

        sizes = DEFAULT_TOKENS.sizes
        typography = DEFAULT_TOKENS.typography
        palette = _active_palette()

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Pass 1: connectors (so indicators paint on top).
            self._paint_connectors(painter, palette)

            # Pass 2: per-step indicator + text.
            for idx, step in enumerate(self._steps):
                cx, cy, hit_rect = self._geom[idx]
                self._paint_indicator(
                    painter, palette, sizes, step, idx, cx, cy
                )
                self._paint_text(
                    painter, palette, typography, sizes, step, cx, cy, hit_rect
                )
        finally:
            painter.end()

    def _paint_connectors(self, painter: QPainter, palette: ThemePalette) -> None:
        sizes = DEFAULT_TOKENS.sizes
        thickness = sizes.workflow_stepper_connector_thickness
        radius = sizes.workflow_stepper_dot_size // 2
        n = len(self._steps)
        for i in range(n - 1):
            cx_a, cy_a, _ = self._geom[i]
            cx_b, cy_b, _ = self._geom[i + 1]
            x1 = cx_a + radius + 2
            x2 = cx_b - radius - 2
            if x2 <= x1:
                continue
            # Connector AFTER step i is colored success only when step i is
            # complete; otherwise default border.
            after_state = self._steps[i].state
            if after_state == "complete":
                color = QColor(palette.status_success_fg)
            else:
                color = QColor(palette.border_default)
            pen = QPen(color, thickness)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawLine(x1, cy_a, x2, cy_b)

    def _paint_indicator(
        self,
        painter: QPainter,
        palette: ThemePalette,
        sizes,
        step: WorkflowStep,
        index: int,
        cx: int,
        cy: int,
    ) -> None:
        size = sizes.workflow_stepper_dot_size
        half = size // 2
        rect = QRect(cx - half, cy - half, size, size)

        state = step.state
        # Resolve fill / outline / glyph color based on state.
        if state == "complete":
            fill = QColor(palette.status_success_fg)
            outline = QColor(palette.status_success_fg)
            glyph_color = QColor(palette.status_success_bg)
        elif state == "active":
            fill = QColor(palette.accent)
            outline = QColor(palette.accent)
            glyph_color = QColor(palette.accent_text)
        elif state == "blocked":
            fill = QColor(palette.status_danger_bg)
            outline = QColor(palette.status_danger_border)
            glyph_color = QColor(palette.status_danger_fg)
        elif state == "skipped":
            fill = QColor(0, 0, 0, 0)
            outline = QColor(palette.border_default)
            glyph_color = QColor(palette.text_muted)
        else:  # pending
            fill = QColor(0, 0, 0, 0)
            outline = QColor(palette.border_strong)
            glyph_color = QColor(palette.text_muted)

        painter.setPen(QPen(outline, 1.5))
        painter.setBrush(fill)
        painter.drawEllipse(rect)

        # Hover highlight ring (clickable + enabled).
        if (
            self._clickable
            and step.enabled
            and self._hover_index == index
        ):
            ring_color = QColor(palette.accent)
            ring_color.setAlpha(120)
            ring_pen = QPen(ring_color, 1.5)
            painter.setPen(ring_pen)
            painter.setBrush(QColor(0, 0, 0, 0))
            ring_rect = rect.adjusted(-2, -2, 2, 2)
            painter.drawEllipse(ring_rect)

        # Glyph.
        painter.setPen(QPen(glyph_color, 1.5))
        font = QFont(painter.font())
        font.setPointSize(DEFAULT_TOKENS.typography.size_small)
        font.setBold(True)
        painter.setFont(font)

        if state == "complete":
            # Draw a check mark as 2-segment polyline.
            cx_, cy_ = rect.center().x(), rect.center().y()
            p1 = QPoint(cx_ - 4, cy_)
            p2 = QPoint(cx_ - 1, cy_ + 3)
            p3 = QPoint(cx_ + 4, cy_ - 3)
            check_pen = QPen(glyph_color, 2)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
        elif state == "blocked":
            painter.drawText(
                rect,
                int(Qt.AlignmentFlag.AlignCenter),
                "!",
            )
        elif state == "skipped":
            slash_pen = QPen(glyph_color, 1.5)
            painter.setPen(slash_pen)
            inset = 4
            painter.drawLine(
                rect.left() + inset,
                rect.bottom() - inset,
                rect.right() - inset,
                rect.top() + inset,
            )
        else:  # pending or active → number
            painter.drawText(
                rect,
                int(Qt.AlignmentFlag.AlignCenter),
                str(index + 1),
            )

    def _paint_text(
        self,
        painter: QPainter,
        palette: ThemePalette,
        typography,
        sizes,
        step: WorkflowStep,
        cx: int,
        cy: int,
        hit_rect: QRect,
    ) -> None:
        gap = sizes.workflow_stepper_label_gap
        label_top = cy + sizes.workflow_stepper_dot_size // 2 + gap
        label_h = 14

        state = step.state

        # Resolve label color + style.
        if state == "blocked":
            label_color = QColor(palette.status_danger_fg)
            italic = False
        elif state == "skipped":
            label_color = QColor(palette.text_muted)
            italic = True
        elif state == "pending":
            label_color = QColor(palette.text_secondary)
            italic = False
        else:  # active / complete
            label_color = QColor(palette.text_primary)
            italic = False

        label_font = QFont(self.font())
        label_font.setPointSize(typography.size_body)
        label_font.setBold(state in ("active", "complete"))
        label_font.setItalic(italic)
        painter.setFont(label_font)

        fm = QFontMetrics(label_font)
        label_text = step.label
        # Reserve space for badge (drawn AFTER label).
        badge_text = step.badge.strip()
        badge_w = 0
        badge_padding_h = 6
        badge_h = sizes.chip_height
        if badge_text:
            badge_fm = QFontMetrics(label_font)
            badge_w = badge_fm.horizontalAdvance(badge_text) + 2 * badge_padding_h

        # Compose: label centered horizontally within the column, with
        # badge floated immediately to the right of the label glyph.
        label_w = fm.horizontalAdvance(label_text)
        total_w = label_w + (4 + badge_w if badge_text else 0)
        col_left = hit_rect.left() + 6
        col_right = hit_rect.right() - 6
        block_left = max(col_left, hit_rect.center().x() - total_w // 2)
        # Clamp so badge does not overflow column.
        if block_left + total_w > col_right:
            block_left = max(col_left, col_right - total_w)

        label_rect = QRect(block_left, label_top, label_w, label_h)
        painter.setPen(label_color)
        painter.drawText(
            label_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            label_text,
        )

        if badge_text:
            badge_left = label_rect.right() + 4
            badge_top = label_top + (label_h - badge_h) // 2
            badge_rect = QRect(badge_left, badge_top, badge_w, badge_h)
            badge_bg = QColor(palette.status_neutral_bg)
            badge_fg = QColor(palette.status_neutral_fg)
            badge_border = QColor(palette.status_neutral_border)
            painter.setPen(QPen(badge_border, 1))
            painter.setBrush(badge_bg)
            painter.drawRoundedRect(
                badge_rect, sizes.chip_radius, sizes.chip_radius
            )
            painter.setPen(badge_fg)
            badge_font = QFont(label_font)
            badge_font.setPointSize(typography.size_small)
            badge_font.setBold(True)
            badge_font.setItalic(False)
            painter.setFont(badge_font)
            painter.drawText(
                badge_rect,
                int(Qt.AlignmentFlag.AlignCenter),
                badge_text,
            )

        # Description (one line, muted).
        if step.description:
            desc_top = label_rect.bottom() + 2
            desc_font = QFont(self.font())
            desc_font.setPointSize(typography.size_small)
            painter.setFont(desc_font)
            desc_color = QColor(palette.text_muted)
            painter.setPen(desc_color)
            desc_fm = QFontMetrics(desc_font)
            desc_text = desc_fm.elidedText(
                step.description,
                Qt.TextElideMode.ElideRight,
                hit_rect.width() - 12,
            )
            desc_rect = QRect(
                hit_rect.left() + 6,
                desc_top,
                hit_rect.width() - 12,
                12,
            )
            painter.drawText(
                desc_rect,
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                desc_text,
            )
