"""RunTimelineWidget — Phase 6 / P6.S1.

A compact horizontal timeline strip that displays the canonical payroll
run state machine as a visual pipeline so the user always knows where
the run sits and what comes next.

States in order: Draft → Calculated → Approved → Posted → Paid → Closed
Terminal side-branches: Voided, Reversed

Design:
  - Each step is a circle node + label below.
  - Completed steps: solid accent fill + check mark.
  - Current step: solid primary accent + ring, label bold.
  - Pending steps: light ghost fill, muted text.
  - Voided / Reversed shown as a branch below the primary pipeline.
  - The widget is read-only (no click actions); the cockpit owns actions.

Architecture: pure UI, no service calls.
"""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import QPointF, QRectF, Qt, QSizeF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from seeker_accounting.shared.ui.styles.palette import ThemePalette, get_palette

# ── Step definitions ────────────────────────────────────────────────────────

_MAIN_STEPS: Final[list[str]] = [
    "draft",
    "calculated",
    "submitted_for_review",
    "approved",
    "posted",
    "paid",
    "closed",
]

_STEP_LABELS: Final[dict[str, str]] = {
    "draft": "Draft",
    "calculated": "Calculated",
    "submitted_for_review": "In Review",
    "approved": "Approved",
    "posted": "Posted",
    "paid": "Paid",
    "closed": "Closed",
    "voided": "Voided",
    "reversed": "Reversed",
}

# Map terminal states to the step they branch from (for the label
# placement).  Voided can happen at draft/calculated/approved, but we
# show it off "draft".  Reversed branches from "posted".
_BRANCH_FROM: Final[dict[str, str]] = {
    "voided": "draft",
    "reversed": "posted",
}

# ── Visual node types ────────────────────────────────────────────────────────

_NODE_DONE = "done"     # completed step
_NODE_CURRENT = "cur"   # active step
_NODE_PENDING = "pend"  # future step
_NODE_BRANCH = "branch" # terminal side-branch (voided/reversed)


class RunTimelineWidget(QWidget):
    """Horizontal read-only timeline for a payroll run state machine.

    Usage::

        tl = RunTimelineWidget(parent)
        tl.set_status("approved")
    """

    _NODE_R: Final[int] = 10   # circle radius
    _STEP_W: Final[int] = 90   # horizontal slot width per step
    _STEP_H: Final[int] = 52   # total widget height

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status: str = "draft"
        self.setMinimumHeight(self._STEP_H)
        self.setMaximumHeight(self._STEP_H + 6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # ── Public ──────────────────────────────────────────────────────────────

    def set_status(self, status_code: str | None) -> None:
        """Update the active status and repaint."""
        self._status = (status_code or "draft").lower()
        self.update()

    # ── Internal ────────────────────────────────────────────────────────────

    def _node_type(self, step: str) -> str:
        status = self._status
        if status in _BRANCH_FROM:
            # Terminal state — mark all main steps as pending; the branch
            # node receives the "branch" type below.
            if step == "draft":
                return _NODE_DONE
            return _NODE_PENDING
        try:
            current_idx = _MAIN_STEPS.index(status)
        except ValueError:
            current_idx = 0
        try:
            step_idx = _MAIN_STEPS.index(step)
        except ValueError:
            return _NODE_PENDING
        if step_idx < current_idx:
            return _NODE_DONE
        if step_idx == current_idx:
            return _NODE_CURRENT
        return _NODE_PENDING

    def _colors(self) -> tuple[QColor, QColor, QColor, QColor, QColor, QColor, QColor]:
        """Return (done_fill, cur_fill, pend_fill, done_text, cur_text, pend_text, connector)."""
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            window = app.palette().color(app.palette().ColorRole.Window) if app else None
            if window is not None and window.lightness() < 128:
                pal = get_palette("dark")
            else:
                pal = get_palette("light")
        except Exception:  # noqa: BLE001
            pal = get_palette("light")

        done_fill = QColor(pal.accent)
        cur_fill = QColor(pal.accent)
        pend_fill = QColor(pal.secondary_surface)
        done_text = QColor(pal.text_primary)
        cur_text = QColor(pal.accent)
        pend_text = QColor(pal.text_muted)
        connector = QColor(pal.border_default)
        return done_fill, cur_fill, pend_fill, done_text, cur_text, pend_text, connector

    def paintEvent(self, _event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        step_count = len(_MAIN_STEPS)
        slot_w = w / step_count
        node_y = self._NODE_R + 8          # vertical centre of circles
        label_y = node_y + self._NODE_R + 4  # baseline for labels

        done_fill, cur_fill, pend_fill, done_text, cur_text, pend_text, connector = (
            self._colors()
        )

        # ── Draw connectors ──────────────────────────────────────────────
        pen = QPen(connector, 1.5)
        painter.setPen(pen)
        for i in range(step_count - 1):
            x1 = slot_w * i + slot_w / 2 + self._NODE_R
            x2 = slot_w * (i + 1) + slot_w / 2 - self._NODE_R
            painter.drawLine(QPointF(x1, node_y), QPointF(x2, node_y))

        # ── Draw nodes ───────────────────────────────────────────────────
        font = self.font()
        small_font = QFont(font)
        small_font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
        painter.setFont(small_font)

        status = self._status
        is_branch = status in _BRANCH_FROM

        for i, step in enumerate(_MAIN_STEPS):
            cx = slot_w * i + slot_w / 2
            ntype = self._node_type(step)

            # Circle fill
            if ntype == _NODE_DONE:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(done_fill)
            elif ntype == _NODE_CURRENT:
                painter.setBrush(cur_fill)
                ring_pen = QPen(cur_fill, 2.5)
                painter.setPen(ring_pen)
            else:  # pending
                painter.setPen(QPen(connector, 1.5))
                painter.setBrush(pend_fill)

            r = self._NODE_R
            painter.drawEllipse(QPointF(cx, node_y), r, r)

            # Check mark for done nodes
            if ntype == _NODE_DONE:
                painter.setPen(QPen(QColor("white"), 1.8))
                path = QPainterPath()
                path.moveTo(cx - r * 0.38, node_y)
                path.lineTo(cx - r * 0.05, node_y + r * 0.42)
                path.lineTo(cx + r * 0.45, node_y - r * 0.40)
                painter.drawPath(path)

            # Current node ring highlight
            if ntype == _NODE_CURRENT:
                ring = QPen(cur_fill.lighter(150), 2.5)
                painter.setPen(ring)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(cx, node_y), r + 3, r + 3)

            # Label
            if ntype == _NODE_DONE:
                lc = done_text
            elif ntype == _NODE_CURRENT:
                lc = cur_text
            else:
                lc = pend_text

            lf = QFont(small_font)
            lf.setBold(ntype == _NODE_CURRENT)
            painter.setFont(lf)
            painter.setPen(lc)
            lbl = _STEP_LABELS.get(step, step.title())
            text_rect = QRectF(cx - slot_w / 2, label_y, slot_w, 16)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                lbl,
            )

        # ── Branch node for terminal states ─────────────────────────────
        if is_branch:
            branch_step = _BRANCH_FROM[status]
            try:
                branch_i = _MAIN_STEPS.index(branch_step)
            except ValueError:
                branch_i = 0
            bx = slot_w * branch_i + slot_w / 2
            branch_y = node_y + self._NODE_R * 2 + 8

            # Arm from the anchor node down to the branch node
            painter.setPen(QPen(QColor("#e34343"), 1.5, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(bx, node_y + self._NODE_R), QPointF(bx, branch_y - self._NODE_R))

            # Branch circle (danger red)
            branch_color = QColor("#e34343")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(branch_color)
            painter.drawEllipse(QPointF(bx, branch_y), self._NODE_R - 1, self._NODE_R - 1)

            # Label
            painter.setPen(branch_color)
            lf2 = QFont(small_font)
            lf2.setBold(True)
            painter.setFont(lf2)
            painter.drawText(
                QRectF(bx - slot_w / 2, branch_y + self._NODE_R + 2, slot_w, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                _STEP_LABELS.get(status, status.title()),
            )

        painter.end()

    def sizeHint(self) -> "QSizeF":  # type: ignore[override]
        from PySide6.QtCore import QSize
        return QSize(len(_MAIN_STEPS) * self._STEP_W, self._STEP_H)


__all__ = ["RunTimelineWidget"]
