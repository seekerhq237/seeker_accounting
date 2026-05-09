"""Floating "Thought Chip" overlay for the Ambient Intelligence layer.

The widget has two modes:

* **collapsed (chip)** — a single short sentence with a tone dot.
  Draggable. Click to expand.
* **expanded (panel)** — same sentence plus detail, confidence label,
  "Why" bullets, and three actions (Dismiss / Snooze / Turn Off).

The chip is parented to the shell root (the same parent the help
overlay uses), so it floats above the workspace stack but below modal
dialogs. It does NOT capture focus on activation — it shows
without activating, so a user who is typing is never interrupted.

Position is persisted as a normalized ratio relative to the parent
size, so the chip stays visually anchored across window resizes.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.dto.ambient_thought_dto import AmbientThoughtDTO
from seeker_accounting.shared.services.ambient_thought_preferences_service import (
    AmbientPosition,
    AmbientThoughtPreferencesService,
)


if TYPE_CHECKING:
    from seeker_accounting.shared.services.ambient_thought_service import (
        AmbientThoughtService,
    )


_log = logging.getLogger(__name__)


_TONE_COLOR = {
    "hint": "#5B8DEF",        # calm blue
    "caution": "#D9822B",     # warm amber
    "projection": "#7A6FF0",  # soft violet
}


class AmbientThoughtOverlay(QWidget):
    """Floating chip/panel that surfaces the current best ambient thought."""

    _CHIP_WIDTH = 320
    _PANEL_WIDTH = 380
    _MIN_HEIGHT = 44

    closed = Signal()

    def __init__(
        self,
        thought_service: "AmbientThoughtService",
        preferences_service: AmbientThoughtPreferencesService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._thought_service = thought_service
        self._prefs = preferences_service
        self._current: AmbientThoughtDTO | None = None
        self._expanded = False

        # Drag state.
        self._drag_active = False
        self._drag_offset = QPoint()

        self.setObjectName("AmbientThoughtOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # ── Card container (rounded surface) ─────────────────────────
        self._card = QFrame(self)
        self._card.setObjectName("AmbientThoughtCard")
        self._card.setStyleSheet(self._card_qss())

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(12, 10, 10, 10)
        card_layout.setSpacing(6)

        # ── Top row: tone dot + summary + chevron ────────────────────
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self._tone_dot = QLabel(self._card)
        self._tone_dot.setFixedSize(8, 8)
        self._tone_dot.setStyleSheet(self._dot_qss("hint"))
        top_row.addWidget(self._tone_dot, 0, Qt.AlignmentFlag.AlignVCenter)

        self._summary_label = QLabel("", self._card)
        self._summary_label.setObjectName("AmbientThoughtSummary")
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet(
            "QLabel { color: #2c3849; font-size: 12px; }"
        )
        top_row.addWidget(self._summary_label, 1)

        self._toggle_btn = QPushButton("⌃", self._card)
        self._toggle_btn.setObjectName("AmbientThoughtToggle")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setStyleSheet(
            "QPushButton { color: #6b7280; border: none; background: transparent; }"
            "QPushButton:hover { color: #111827; }"
        )
        self._toggle_btn.clicked.connect(self._toggle_expanded)
        top_row.addWidget(self._toggle_btn, 0, Qt.AlignmentFlag.AlignTop)

        card_layout.addLayout(top_row)

        # ── Expanded panel (created lazily-visible) ──────────────────
        self._expanded_container = QFrame(self._card)
        self._expanded_container.setObjectName("AmbientThoughtExpanded")
        self._expanded_container.setVisible(False)
        ec_layout = QVBoxLayout(self._expanded_container)
        ec_layout.setContentsMargins(0, 6, 0, 0)
        ec_layout.setSpacing(6)

        self._confidence_label = QLabel("", self._expanded_container)
        self._confidence_label.setStyleSheet(
            "QLabel { color: #6b7280; font-size: 10px; text-transform: uppercase; "
            "letter-spacing: 0.5px; }"
        )
        ec_layout.addWidget(self._confidence_label)

        self._detail_label = QLabel("", self._expanded_container)
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet(
            "QLabel { color: #374151; font-size: 11px; }"
        )
        ec_layout.addWidget(self._detail_label)

        self._why_label = QLabel("", self._expanded_container)
        self._why_label.setWordWrap(True)
        self._why_label.setStyleSheet(
            "QLabel { color: #6b7280; font-size: 11px; }"
        )
        ec_layout.addWidget(self._why_label)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 4, 0, 0)
        actions_row.setSpacing(6)

        self._dismiss_btn = self._action_btn("Dismiss")
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        actions_row.addWidget(self._dismiss_btn)

        self._snooze_btn = self._action_btn("Snooze 1h")
        self._snooze_btn.clicked.connect(self._on_snooze_hour)
        actions_row.addWidget(self._snooze_btn)

        self._mute_btn = self._action_btn("Mute this")
        self._mute_btn.clicked.connect(self._on_mute_this)
        actions_row.addWidget(self._mute_btn)

        actions_row.addStretch(1)

        self._off_btn = self._action_btn("Turn Off")
        self._off_btn.clicked.connect(self._on_turn_off)
        actions_row.addWidget(self._off_btn)

        ec_layout.addLayout(actions_row)
        card_layout.addWidget(self._expanded_container)

        # ── Outer layout: a single card ──────────────────────────────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._card)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._apply_chip_size()

        # ── Idle / debounce timer ────────────────────────────────────
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(500)  # 500ms debounce
        self._refresh_timer.timeout.connect(self._do_refresh)

        # ── Re-position when the parent resizes ──────────────────────
        if parent is not None:
            parent.installEventFilter(self)

        # ── React to preference changes from anywhere in the shell ──
        self._prefs.preferences_changed.connect(self._on_preferences_changed)

        # ── Modal dialog monitoring ───────────────────────────────────
        # When a modal dialog that implements `ambient_context_changed` opens,
        # connect to it so the overlay refreshes whenever draft state changes.
        self._connected_dialog: "QWidget | None" = None
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.focusChanged.connect(self._on_focus_changed)
        except Exception:
            pass

        # Start hidden until the first refresh produces something.
        self.hide()

    # ── Public API ───────────────────────────────────────────────────

    def request_refresh(self) -> None:
        """Coalesced refresh trigger; safe to call many times."""
        self._refresh_timer.start()

    def refresh_now(self) -> None:
        """Synchronous refresh — for shell hooks where we know we want it."""
        self._refresh_timer.stop()
        self._do_refresh()

    def set_thought(self, thought: AmbientThoughtDTO | None) -> None:
        """Render a specific thought (or hide if None)."""
        if thought is None:
            self._current = None
            self.hide()
            return

        self._current = thought
        self._summary_label.setText(thought.summary or "")
        self._tone_dot.setStyleSheet(self._dot_qss(thought.tone))
        self._confidence_label.setText(thought.confidence_label or "")
        self._detail_label.setText(thought.detail or "")
        self._detail_label.setVisible(bool(thought.detail))
        if thought.why_items:
            self._why_label.setText(
                "Why: " + " · ".join(thought.why_items)
            )
            self._why_label.setVisible(True)
        else:
            self._why_label.setText("")
            self._why_label.setVisible(False)

        self._apply_chip_size()
        self._reposition_from_prefs()
        if not self.isVisible():
            self.show()
            self.raise_()

    # ── Refresh pipeline ─────────────────────────────────────────────

    def _do_refresh(self) -> None:
        if not self._prefs.is_enabled() or self._prefs.is_snoozed():
            self.set_thought(None)
            return

        # Build context from the current shell state. Importing here so
        # that constructing the overlay doesn't require a context service.
        try:
            context_service = self._resolve_context_service()
            page = self._resolve_current_page()
            context = context_service.build(page=page)
        except Exception:
            _log.debug("AmbientThoughtOverlay: context build failed.", exc_info=True)
            self.set_thought(None)
            return

        try:
            best = self._thought_service.get_best_thought(context)
        except Exception:
            _log.debug(
                "AmbientThoughtOverlay: thought_service.get_best_thought failed.",
                exc_info=True,
            )
            best = None

        if best is None:
            self.set_thought(None)
            return

        self._thought_service.mark_shown(best)
        self.set_thought(best)

    def _resolve_context_service(self):
        # Lazy import — overlay can live without the context service in
        # tests that hand-feed thoughts via `set_thought`.
        from seeker_accounting.shared.services.ambient_thought_context_service import (
            AmbientThoughtContextService,
        )

        sr = getattr(self._thought_service, "_sr", None)
        if sr is None:
            raise RuntimeError("ThoughtService has no service_registry attribute")
        return AmbientThoughtContextService(sr)

    def _resolve_current_page(self) -> QWidget | None:
        # Walk up to the shell root, then ask the workspace_host for the
        # current page. The host is identified duck-typed by the
        # presence of `current_page()`.
        node: QWidget | None = self.parent() if isinstance(self.parent(), QWidget) else None
        seen: set[int] = set()
        while node is not None and id(node) not in seen:
            seen.add(id(node))
            host = self._find_workspace_host(node)
            if host is not None:
                try:
                    return host.current_page()
                except Exception:
                    return None
            node = node.parentWidget()
        return None

    @staticmethod
    def _find_workspace_host(root: QWidget) -> QWidget | None:
        # Breadth-first search bounded to a small fan-out; in practice
        # the shell tree is shallow and the host is one or two levels in.
        queue: list[QWidget] = [root]
        seen: set[int] = set()
        while queue:
            node = queue.pop(0)
            if id(node) in seen:
                continue
            seen.add(id(node))
            if (
                node.metaObject().className() == "WorkspaceHost"
                or callable(getattr(node, "current_page", None))
                and node.objectName() == "WorkspaceFrame"
            ):
                return node
            for child in node.findChildren(QWidget):
                if child.objectName() == "WorkspaceFrame":
                    return child
            return None
        return None

    # ── Expand / collapse ────────────────────────────────────────────

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._expanded_container.setVisible(self._expanded)
        self._toggle_btn.setText("⌄" if self._expanded else "⌃")
        self._apply_chip_size()
        self._reposition_from_prefs()

    def _apply_chip_size(self) -> None:
        width = self._PANEL_WIDTH if self._expanded else self._CHIP_WIDTH
        self.setFixedWidth(width)
        # Let layout pick the height; just make sure there's a sane min.
        self._card.adjustSize()
        self.adjustSize()
        self.setMinimumHeight(self._MIN_HEIGHT)

    # ── Action handlers ──────────────────────────────────────────────

    def _on_dismiss(self) -> None:
        if self._current is not None:
            self._thought_service.mark_dismissed(self._current)
        self.set_thought(None)

    def _on_snooze_hour(self) -> None:
        self._prefs.snooze_for(60)
        self.set_thought(None)

    def _on_mute_this(self) -> None:
        """Permanently mute the current thought code for this user."""
        if self._current is not None:
            self._prefs.mute(self._current.thought_code)
        self.set_thought(None)
        # Immediately try to surface the next best thought (different code).
        self.request_refresh()

    def _on_turn_off(self) -> None:
        self._prefs.set_enabled(False)
        self.set_thought(None)

    def _on_preferences_changed(self) -> None:
        if not self._prefs.is_enabled() or self._prefs.is_snoozed():
            self.set_thought(None)
        else:
            self.request_refresh()

    def _on_focus_changed(self, _old: "QWidget | None", _new: "QWidget | None") -> None:
        """Track active modal dialogs to stay in sync with their draft context."""
        try:
            from PySide6.QtWidgets import QApplication
            modal = QApplication.activeModalWidget()
            if modal is self._connected_dialog:
                return  # nothing changed

            # ── Disconnect from the previous dialog ───────────────────
            if self._connected_dialog is not None:
                try:
                    sig = getattr(self._connected_dialog, "ambient_context_changed", None)
                    if sig is not None:
                        sig.disconnect(self.request_refresh)
                except Exception:
                    pass
                self._connected_dialog = None

            # ── Connect to the new dialog ─────────────────────────────
            if modal is not None:
                sig = getattr(modal, "ambient_context_changed", None)
                if sig is not None:
                    sig.connect(self.request_refresh)
                    self._connected_dialog = modal
                    self.request_refresh()
        except Exception:
            pass

    # ── Drag handling ────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._drag_offset = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_active:
            parent = self.parentWidget()
            if parent is None:
                return
            new_top_left = self.mapToParent(event.position().toPoint() - self._drag_offset)
            new_top_left = self._clamp_to_parent(new_top_left)
            self.move(new_top_left)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_active and event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._persist_position()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _clamp_to_parent(self, top_left: QPoint) -> QPoint:
        parent = self.parentWidget()
        if parent is None:
            return top_left
        max_x = max(0, parent.width() - self.width())
        max_y = max(0, parent.height() - self.height())
        return QPoint(min(max(top_left.x(), 0), max_x), min(max(top_left.y(), 0), max_y))

    def _persist_position(self) -> None:
        parent = self.parentWidget()
        if parent is None or parent.width() <= 0 or parent.height() <= 0:
            return
        # Anchor by which corner is closer; ratios are stored relative to
        # the chosen anchor so resizes stay visually stable.
        center = self.geometry().center()
        on_right = center.x() > parent.width() / 2
        on_bottom = center.y() > parent.height() / 2
        if on_right and on_bottom:
            anchor = "bottom_right"
        elif on_right and not on_bottom:
            anchor = "top_right"
        elif not on_right and on_bottom:
            anchor = "bottom_left"
        else:
            anchor = "top_left"
        x_ratio = (self.x() + self.width() / 2) / parent.width()
        y_ratio = (self.y() + self.height() / 2) / parent.height()
        self._prefs.set_position(
            AmbientPosition(anchor=anchor, x_ratio=float(x_ratio), y_ratio=float(y_ratio))  # type: ignore[arg-type]
        )

    # ── Positioning ──────────────────────────────────────────────────

    def _reposition_from_prefs(self) -> None:
        parent = self.parentWidget()
        if parent is None or parent.width() <= 0 or parent.height() <= 0:
            return
        position = self._prefs.position()
        cx = position.x_ratio * parent.width()
        cy = position.y_ratio * parent.height()
        new_x = int(cx - self.width() / 2)
        new_y = int(cy - self.height() / 2)
        new_top_left = self._clamp_to_parent(QPoint(new_x, new_y))
        self.move(new_top_left)

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # type: ignore[override]
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._reposition_from_prefs()
        return super().eventFilter(watched, event)

    # ── Helpers ──────────────────────────────────────────────────────

    def _action_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text, self._expanded_container)
        btn.setObjectName("AmbientThoughtAction")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        btn.setStyleSheet(
            "QPushButton {"
            " color: #374151;"
            " background: rgba(15, 23, 42, 0.04);"
            " border: 1px solid rgba(15, 23, 42, 0.06);"
            " border-radius: 6px;"
            " padding: 3px 8px;"
            " font-size: 11px;"
            "}"
            "QPushButton:hover {"
            " background: rgba(15, 23, 42, 0.08);"
            "}"
        )
        return btn

    @staticmethod
    def _dot_qss(tone: str) -> str:
        color = _TONE_COLOR.get(tone, _TONE_COLOR["hint"])
        return (
            "QLabel {"
            f" background: {color};"
            " border-radius: 4px;"
            "}"
        )

    @staticmethod
    def _card_qss() -> str:
        return (
            "QFrame#AmbientThoughtCard {"
            " background: rgba(255, 255, 255, 0.97);"
            " border: 1px solid rgba(15, 23, 42, 0.08);"
            " border-radius: 10px;"
            "}"
        )
