from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from enum import Enum, auto

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLabel,
    QPushButton,
    QWidget,
)


# ── Brand constants ─────────────────────────────────────────────────────
_BG_COLOR = QColor("#F7F8FC")
_TITLEBAR_BG = QColor("#E6EAF2")
_BADGE_BLUE = QColor("#2F66E8")
_BADGE_GLOW = QColor("#5A86F2")
_TEXT_COLOR = QColor("#182230")
_TEXT_SECONDARY = QColor("#526071")
_TEXT_MUTED = QColor("#7A8797")
_STATUS_COLOR = QColor("#8E99A8")
_WHITE = QColor("#FFFFFF")

_SPLASH_W = 1020
_SPLASH_H = 613
_TITLEBAR_H = 32
_CORNER_RADIUS = 12

# ── Layout constants (shared axis for splash and landing) ───────────────
_BADGE_SPLASH_CX = _SPLASH_W / 2.0
_BADGE_SPLASH_CY = _SPLASH_H * 0.42
_BADGE_LANDING_CX = _SPLASH_W / 2.0
_BADGE_LANDING_CY = _SPLASH_H * 0.24

_BADGE_SPLASH_R = 112.0
_BADGE_LANDING_R = _BADGE_SPLASH_R * 0.76

_SYMBOL_RATIO = 1.0

_TITLE_Y = _SPLASH_H * 0.54
_TAGLINE_Y = _SPLASH_H * 0.615
_CTA_Y = _SPLASH_H * 0.72
_SECONDARY_Y = _SPLASH_H * 0.82
_VERSION_X = 28
_VERSION_Y = _SPLASH_H - 24
_STATUS_Y = _SPLASH_H - 26

# ── Timeline constants (seconds) ───────────────────────────────────────
_ATMOS_START = 0.00
_ATMOS_END = 0.16

_SPINE_START = 0.10
_SPINE_END = 0.62

_DIAG_START = 0.42
_DIAG_END = 0.90

_DOT_START = 0.82
_DOT_END = 1.02

_SETTLE_START = 0.96
_SETTLE_END = 1.14

_BADGE_START = 1.08
_BADGE_END = 1.36

_MSG_START = 1.28
_MSG_END = 1.58

_TRANSFORM_START = 1.52
_TRANSFORM_END = 2.02

_TITLE_START = 1.86
_TITLE_END = 2.18

_TAGLINE_START = 2.02
_TAGLINE_END = 2.28

_CTA_START = 2.16
_CTA_END = 2.42

_SECONDARY_START = 2.26
_SECONDARY_END = 2.52

_ANIMATION_GATE = 2.52

_PARTICLE_COUNT = 14


# ── State machine ──────────────────────────────────────────────────────

class _Phase(Enum):
    BOOT = auto()
    ATMOSPHERE = auto()
    STRUCTURE_BUILD = auto()
    DIAGONAL_SWEEP = auto()
    DOT_SETTLE = auto()
    SYMBOL_SETTLE = auto()
    BADGE_BIRTH = auto()
    MESSAGE_BEAT = auto()
    LANDING_TRANSFORM = auto()
    LANDING_REVEAL = auto()
    HOLD_READY = auto()
    FAILED = auto()


# ── Symbol piece groups ────────────────────────────────────────────────

class _Group(Enum):
    SPINE = auto()
    DIAGONAL = auto()
    DOT = auto()


# ── Easing functions ───────────────────────────────────────────────────

def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    t -= 1.0
    return t * t * t + 1.0


def _ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    p = -2.0 * t + 2.0
    return 1.0 - p * p * p / 2.0


def _ease_out_back_soft(t: float, overshoot: float = 1.2) -> float:
    """Mild overshoot-then-settle — used for dots only."""
    t = max(0.0, min(1.0, t))
    t -= 1.0
    return t * t * ((overshoot + 1.0) * t + overshoot) + 1.0


def _ease_out_expo(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t >= 1.0:
        return 1.0
    return 1.0 - math.pow(2.0, -10.0 * t)


def _ease_out_quint(t: float) -> float:
    t = max(0.0, min(1.0, t))
    t -= 1.0
    return t * t * t * t * t + 1.0


# ── Color interpolation ───────────────────────────────────────────────

def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


# ── Data structures ───────────────────────────────────────────────────

@dataclass(slots=True)
class _Particle:
    x: float
    y: float
    radius: float
    alpha: float
    dx: float
    dy: float


@dataclass(frozen=True, slots=True)
class _SymbolPiece:
    name: str
    group: _Group
    norm_cx: float
    norm_cy: float
    origin_dx: float
    origin_dy: float
    t_start: float
    t_end: float
    start_rotation: float


def _build_symbol_pieces() -> list[_SymbolPiece]:
    """Define the six named components of the Seeker mark."""
    return [
        _SymbolPiece(
            name="bar_vertical", group=_Group.SPINE,
            norm_cx=0.0, norm_cy=0.0,
            origin_dx=0.0, origin_dy=-40.0,
            t_start=_SPINE_START, t_end=_SPINE_END,
            start_rotation=0.0,
        ),
        _SymbolPiece(
            name="bar_horizontal", group=_Group.SPINE,
            norm_cx=0.0, norm_cy=0.0,
            origin_dx=-55.0, origin_dy=0.0,
            t_start=_SPINE_START + 0.06, t_end=_SPINE_END + 0.04,
            start_rotation=0.0,
        ),
        _SymbolPiece(
            name="diag_upper_right", group=_Group.DIAGONAL,
            norm_cx=0.40, norm_cy=-0.40,
            origin_dx=45.0, origin_dy=-45.0,
            t_start=_DIAG_START, t_end=_DIAG_END,
            start_rotation=10.0,
        ),
        _SymbolPiece(
            name="diag_lower_left", group=_Group.DIAGONAL,
            norm_cx=-0.40, norm_cy=0.40,
            origin_dx=-45.0, origin_dy=45.0,
            t_start=_DIAG_START + 0.06, t_end=_DIAG_END + 0.02,
            start_rotation=-10.0,
        ),
        _SymbolPiece(
            name="dot_upper_left", group=_Group.DOT,
            norm_cx=-0.46, norm_cy=-0.46,
            origin_dx=-20.0, origin_dy=-20.0,
            t_start=_DOT_START, t_end=_DOT_END,
            start_rotation=0.0,
        ),
        _SymbolPiece(
            name="dot_lower_right", group=_Group.DOT,
            norm_cx=0.46, norm_cy=0.46,
            origin_dx=20.0, origin_dy=20.0,
            t_start=_DOT_START + 0.04, t_end=_DOT_END + 0.04,
            start_rotation=0.0,
        ),
    ]


# ── Vector path factories ──────────────────────────────────────────────

def _path_bar_vertical(hs: float) -> QPainterPath:
    w = hs * 0.25
    h = hs * 2.4
    r = w / 2.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), r, r)
    return path


def _path_bar_horizontal(hs: float) -> QPainterPath:
    w = hs * 2.4
    h = hs * 0.25
    r = h / 2.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), r, r)
    return path


def _path_diag_upper_right(hs: float) -> QPainterPath:
    length = hs * 1.20
    width = hs * 0.25
    r = width / 2.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, -width / 2, length, width), r, r)
    xf = QTransform()
    xf.rotate(-45.0)
    return xf.map(path)


def _path_diag_lower_left(hs: float) -> QPainterPath:
    length = hs * 1.20
    width = hs * 0.25
    r = width / 2.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(-length, -width / 2, length, width), r, r)
    xf = QTransform()
    xf.rotate(-45.0)
    return xf.map(path)


def _path_dot(hs: float, cx_norm: float, cy_norm: float) -> QPainterPath:
    radius = hs * 0.19
    cx = cx_norm * hs
    cy = cy_norm * hs
    path = QPainterPath()
    path.addEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
    return path


_PATH_FACTORIES: dict[str, object] = {
    "bar_vertical": lambda hs: _path_bar_vertical(hs),
    "bar_horizontal": lambda hs: _path_bar_horizontal(hs),
    "diag_upper_right": lambda hs: _path_diag_upper_right(hs),
    "diag_lower_left": lambda hs: _path_diag_lower_left(hs),
    "dot_upper_left": lambda hs: _path_dot(hs, -0.46, -0.46),
    "dot_lower_right": lambda hs: _path_dot(hs, 0.46, 0.46),
}


# ═══════════════════════════════════════════════════════════════════════
#  AnimatedSplashScreen
# ═══════════════════════════════════════════════════════════════════════

class AnimatedSplashScreen(QWidget):
    """Animated splash that transforms into the interactive landing surface."""

    ready_to_close = Signal()
    login_requested = Signal()
    create_organisation_requested = Signal()
    system_admin_requested = Signal()
    license_requested = Signal()
    get_started_requested = Signal()
    _status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(_SPLASH_W, _SPLASH_H + _TITLEBAR_H)

        self._drag_pos: object = None

        # App icon scaled for the titlebar (18 × 18).
        try:
            from seeker_accounting.config.paths import app_icon_path as _app_icon_path
            _icon_path = _app_icon_path()
            self._titlebar_icon: QPixmap | None = (
                QPixmap(str(_icon_path)).scaled(
                    18, 18,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if _icon_path.exists() else None
            )
        except Exception:
            self._titlebar_icon = None

        self._pieces = _build_symbol_pieces()
        self._particles = self._create_particles()

        self._phase = _Phase.BOOT
        self._status_text = ""
        self._preload_done = False
        self._preload_failed_msg: str | None = None
        self._start_time: float | None = None
        self._interactive = False

        self._status_changed.connect(self._on_status_changed)

        self._msg_font = QFont("Segoe UI", 18)
        self._msg_font.setWeight(QFont.Weight.Medium)
        self._msg_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.4)

        self._status_font = QFont("Segoe UI", 9)
        self._status_font.setWeight(QFont.Weight.Normal)

        # Landing widgets — hidden until landing reveal phase
        self._title_label = self._make_title_label()
        self._tagline_label = self._make_tagline_label()
        self._login_btn = self._make_login_button()
        self._create_org_btn = self._make_create_org_button()
        self._version_label = self._make_version_label()
        self._admin_btn = self._make_admin_button()
        self._license_btn = self._make_license_button()
        self._help_btn = self._make_help_button()
        self._close_btn = self._make_close_button()

        self._landing_widgets: list[tuple[QWidget, float, float, float]] = [
            (self._title_label, _TITLE_START, _TITLE_Y, 14.0),
            (self._tagline_label, _TAGLINE_START, _TAGLINE_Y, 8.0),
            (self._login_btn, _CTA_START, _CTA_Y, 10.0),
            (self._create_org_btn, _SECONDARY_START, _SECONDARY_Y, 6.0),
        ]

        for widget, _, _, _ in self._landing_widgets:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)
            widget.setVisible(False)

        self._version_label.setVisible(False)
        self._admin_btn.setVisible(False)
        self._license_btn.setVisible(False)
        self._help_btn.setVisible(False)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_tick)

    # ── Widget factories ───────────────────────────────────────────────

    def _make_title_label(self) -> QLabel:
        label = QLabel(self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setText(
            '<span style="font-weight:700;">Seeker</span>'
            '<span style="font-weight:400;"> Accounting</span>'
        )
        label.setStyleSheet(
            f"QLabel {{ color: {_TEXT_COLOR.name()}; font-size: 28px;"
            f" font-family: 'Segoe UI'; background: transparent; }}"
        )
        label.setFixedWidth(_SPLASH_W)
        label.adjustSize()
        label.setFixedHeight(label.sizeHint().height())
        label.move(0, _TITLEBAR_H + int(_TITLE_Y - label.height() / 2))
        return label

    def _make_tagline_label(self) -> QLabel:
        label = QLabel("Built for Business Clarity.", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"QLabel {{ color: {_TEXT_SECONDARY.name()}; font-size: 13px;"
            f" font-weight: 500; font-family: 'Segoe UI'; background: transparent; }}"
        )
        label.setFixedWidth(_SPLASH_W)
        label.adjustSize()
        label.setFixedHeight(label.sizeHint().height())
        label.move(0, _TITLEBAR_H + int(_TAGLINE_Y - label.height() / 2))
        return label

    def _make_login_button(self) -> QPushButton:
        btn = QPushButton("LOG IN", self)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(240, 46)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {_BADGE_BLUE.name()};"
            f"  color: white; border: none; border-radius: 11px;"
            f"  font-size: 14px; font-weight: 600; font-family: 'Segoe UI';"
            f"}}"
            f"QPushButton:hover {{ background-color: #2558CC; }}"
            f"QPushButton:pressed {{ background-color: #1E4BB5; }}"
        )
        btn.move(int((_SPLASH_W - 240) / 2), _TITLEBAR_H + int(_CTA_Y - 23))
        btn.clicked.connect(self.login_requested.emit)
        btn.setEnabled(False)
        return btn

    def _make_create_org_button(self) -> QPushButton:
        btn = QPushButton("Create Organisation", self)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; border: none;"
            f"  color: {_TEXT_MUTED.name()}; font-size: 13px;"
            f"  font-weight: 500; font-family: 'Segoe UI'; padding: 0;"
            f"}}"
            f"QPushButton:hover {{ color: {_BADGE_BLUE.name()}; }}"
        )
        btn.adjustSize()
        btn.move(int((_SPLASH_W - btn.width()) / 2), _TITLEBAR_H + int(_SECONDARY_Y - btn.height() / 2))
        btn.clicked.connect(self.create_organisation_requested.emit)
        btn.setEnabled(False)
        return btn

    def _make_version_label(self) -> QLabel:
        label = QLabel("", self)
        label.setStyleSheet(
            f"QLabel {{ color: {_TEXT_MUTED.name()}; font-size: 11px;"
            f" font-family: 'Segoe UI'; background: transparent; }}"
        )
        label.move(int(_VERSION_X), _TITLEBAR_H + int(_VERSION_Y))
        return label

    def _make_admin_button(self) -> QPushButton:
        btn = QPushButton("\U0001f527", self)
        btn.setObjectName("LandingAdminTrigger")
        btn.setFixedSize(28, 28)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("System Administration")
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 14px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.04); border-radius: 6px; }"
        )
        btn.move(int(_VERSION_X), _TITLEBAR_H + int(_VERSION_Y - 32))
        btn.clicked.connect(self.system_admin_requested.emit)
        btn.setEnabled(False)
        return btn

    def _make_license_button(self) -> QPushButton:
        btn = QPushButton("\U0001f511", self)
        btn.setObjectName("LandingLicenseTrigger")
        btn.setFixedSize(28, 28)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("License Management")
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 14px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.04); border-radius: 6px; }"
        )
        btn.move(int(_VERSION_X) + 32, _TITLEBAR_H + int(_VERSION_Y - 32))
        btn.clicked.connect(self.license_requested.emit)
        btn.setEnabled(False)
        return btn

    def _make_help_button(self) -> QPushButton:
        btn = QPushButton("\u2139\ufe0f", self)
        btn.setObjectName("LandingHelpTrigger")
        btn.setFixedSize(28, 28)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Get Started Guide")
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 14px; }"
            "QPushButton:hover { background: rgba(0,0,0,0.04); border-radius: 6px; }"
        )
        btn.move(int(_VERSION_X) + 64, _TITLEBAR_H + int(_VERSION_Y - 32))
        btn.clicked.connect(self.get_started_requested.emit)
        btn.setEnabled(False)
        return btn

    def _make_close_button(self) -> QPushButton:
        btn = QPushButton("×", self)
        btn.setFixedSize(32, _TITLEBAR_H)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Close")
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent; border: none;"
            f"  color: {_TEXT_SECONDARY.name()}; font-size: 18px; font-weight: 300;"
            f"  padding-bottom: 2px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background: rgba(0,0,0,0.10);"
            f"  border-top-right-radius: {_CORNER_RADIUS}px;"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background: rgba(0,0,0,0.18);"
            f"  border-top-right-radius: {_CORNER_RADIUS}px;"
            f"}}"
        )
        btn.move(_SPLASH_W - 32, 0)
        btn.clicked.connect(self.close)
        btn.raise_()
        return btn

    # ── Public API ─────────────────────────────────────────────────────

    def start_animation(self) -> None:
        self._start_time = time.perf_counter()
        self._phase = _Phase.ATMOSPHERE
        self._timer.start()

    def show_as_landing(self) -> None:
        """Skip the intro animation and show the window immediately in the
        fully-settled landing state.  Used when returning from the shell on
        logout so the user sees the landing surface without re-watching the
        splash sequence."""
        # Fake a start time far enough in the past that every phase is done.
        self._start_time = time.perf_counter() - (_ANIMATION_GATE + 1.0)
        self._phase = _Phase.HOLD_READY
        self._preload_done = True

        # Snap all landing widgets to their final positions and full opacity.
        elapsed = _ANIMATION_GATE + 1.0
        for widget, show_time, final_y, _rise in self._landing_widgets:
            widget.setVisible(True)
            effect = widget.graphicsEffect()
            if isinstance(effect, QGraphicsOpacityEffect):
                effect.setOpacity(1.0)
            target_y = int(final_y - widget.height() / 2)
            widget.move(widget.x(), target_y)

        self._version_label.setVisible(True)
        self._admin_btn.setVisible(True)
        self._license_btn.setVisible(True)
        self._help_btn.setVisible(True)

        self._try_enable_interaction()
        # Keep the low-frequency repaint timer alive for hover effects.
        self._timer.setInterval(100)
        self._timer.start()

    def set_status(self, message: str) -> None:
        self._status_changed.emit(message)

    def mark_preload_done(self) -> None:
        self._preload_done = True
        self._try_enable_interaction()

    def mark_preload_failed(self, error_msg: str) -> None:
        self._preload_failed_msg = error_msg
        self._preload_done = True
        self._phase = _Phase.FAILED

    def set_version_text(self, text: str) -> None:
        self._version_label.setText(text)
        self._version_label.adjustSize()

    # ── Internals ──────────────────────────────────────────────────────

    def _on_status_changed(self, message: str) -> None:
        self._status_text = message

    def _try_enable_interaction(self) -> None:
        if not self._preload_done or self._phase != _Phase.HOLD_READY:
            return
        if self._interactive:
            return
        if self._preload_failed_msg is not None:
            self._phase = _Phase.FAILED
            self.ready_to_close.emit()
            return
        self._interactive = True
        self._login_btn.setEnabled(True)
        self._create_org_btn.setEnabled(True)
        self._admin_btn.setEnabled(True)
        self._license_btn.setEnabled(True)
        self._help_btn.setEnabled(True)
        self.ready_to_close.emit()

    def _update_phase(self, elapsed: float) -> None:
        if self._phase == _Phase.FAILED:
            return
        if elapsed < _ATMOS_END:
            self._phase = _Phase.ATMOSPHERE
        elif elapsed < _DIAG_START:
            self._phase = _Phase.STRUCTURE_BUILD
        elif elapsed < _DOT_START:
            self._phase = _Phase.DIAGONAL_SWEEP
        elif elapsed < _SETTLE_START:
            self._phase = _Phase.DOT_SETTLE
        elif elapsed < _BADGE_START:
            self._phase = _Phase.SYMBOL_SETTLE
        elif elapsed < _MSG_START:
            self._phase = _Phase.BADGE_BIRTH
        elif elapsed < _TRANSFORM_START:
            self._phase = _Phase.MESSAGE_BEAT
        elif elapsed < _TITLE_START:
            self._phase = _Phase.LANDING_TRANSFORM
        elif elapsed < _ANIMATION_GATE:
            self._phase = _Phase.LANDING_REVEAL
        else:
            self._phase = _Phase.HOLD_READY

    def _on_tick(self) -> None:
        if self._start_time is None:
            return
        elapsed = time.perf_counter() - self._start_time
        self._update_phase(elapsed)
        self._animate_landing_widgets(elapsed)

        if self._phase == _Phase.HOLD_READY:
            if not self._interactive:
                self._try_enable_interaction()
            if self._interactive and self._timer.interval() < 100:
                self._timer.setInterval(100)

        self.update()

    def _animate_landing_widgets(self, elapsed: float) -> None:
        for widget, show_time, final_y, rise_px in self._landing_widgets:
            if elapsed < show_time:
                continue
            if not widget.isVisible():
                widget.setVisible(True)
            t = min(1.0, (elapsed - show_time) / 0.30)
            progress = _ease_out_quint(t)
            effect = widget.graphicsEffect()
            if isinstance(effect, QGraphicsOpacityEffect):
                effect.setOpacity(progress)
            offset_y = rise_px * (1.0 - progress)
            target_y = final_y - widget.height() / 2
            widget.move(widget.x(), int(target_y + offset_y))

        if elapsed >= _SECONDARY_START and not self._version_label.isVisible():
            self._version_label.setVisible(True)
            self._admin_btn.setVisible(True)
            self._license_btn.setVisible(True)
            self._help_btn.setVisible(True)

    def _create_particles(self) -> list[_Particle]:
        particles = []
        for _ in range(_PARTICLE_COUNT):
            particles.append(_Particle(
                x=random.uniform(0, _SPLASH_W),
                y=random.uniform(0, _SPLASH_H),
                radius=random.uniform(1.0, 2.2),
                alpha=random.uniform(0.03, 0.10),
                dx=random.uniform(-0.12, 0.12),
                dy=random.uniform(-0.08, 0.08),
            ))
        return particles

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        screen = self.screen()
        if screen is not None:
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < _TITLEBAR_H:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        else:
            self._drag_pos = None

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_pos = None

    # ── Paint ──────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Clear to transparent, then fill a rounded rect as the window shape.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        _win_shape = QPainterPath()
        _win_shape.addRoundedRect(QRectF(self.rect()), _CORNER_RADIUS, _CORNER_RADIUS)
        p.setClipPath(_win_shape)
        p.fillPath(_win_shape, QBrush(_BG_COLOR))
        self._paint_titlebar(p)

        if self._start_time is None:
            p.end()
            return

        elapsed = time.perf_counter() - self._start_time

        # All content painting is in the space below the title bar.
        p.save()
        p.translate(0, _TITLEBAR_H)
        self._paint_particles(p, elapsed)

        badge_t = self._badge_progress(elapsed)
        transform_t = self._transform_progress(elapsed)
        badge_cx, badge_cy, badge_r = self._current_badge_geometry(transform_t)

        # Outer disc — larger blue circle drawn behind the badge, giving
        # breathing room between the mark and the visible circle edge.
        # Fades in alongside the badge fill phase; inner disc and symbol
        # are painted on top, so nothing about them changes.
        if badge_t > 0.64:
            outer_t = _ease_out_expo(min(1.0, (badge_t - 0.64) / 0.36))
            outer_color = QColor(_BADGE_BLUE)
            outer_color.setAlpha(int(255 * outer_t))
            outer_r = badge_r * 1.26
            p.save()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(outer_color))
            p.drawEllipse(QRectF(
                badge_cx - outer_r, badge_cy - outer_r,
                outer_r * 2, outer_r * 2,
            ))
            p.restore()

        if badge_t > 0.0:
            self._paint_badge_disc(p, badge_cx, badge_cy, badge_r, badge_t)

        symbol_color = self._current_symbol_color(badge_t)
        half_size = self._current_symbol_half_size(transform_t)

        # Clip symbol to badge disc once the disc fill is underway,
        # so bar tips terminate cleanly at the disc edge (matching the real logo).
        clip_to_disc = badge_t > 0.6
        if clip_to_disc:
            p.save()
            clip = QPainterPath()
            clip.addEllipse(QRectF(
                badge_cx - badge_r, badge_cy - badge_r,
                badge_r * 2, badge_r * 2,
            ))
            p.setClipPath(clip)

        self._paint_symbol(p, elapsed, badge_cx, badge_cy, half_size, symbol_color)

        if clip_to_disc:
            p.restore()

        if badge_t >= 0.9:
            self._paint_glow(p, badge_cx, badge_cy, badge_r, badge_t)

        self._paint_message(p, elapsed)
        self._paint_status(p, elapsed)

        p.restore()  # end content translate

        p.end()

    # ── Paint helpers ──────────────────────────────────────────────────

    def _paint_titlebar(self, p: QPainter) -> None:
        # Light blue-grey titlebar background
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_TITLEBAR_BG))
        p.drawRect(QRectF(0, 0, _SPLASH_W, _TITLEBAR_H))
        p.restore()

        # Subtle separator between titlebar and content area
        sep = QColor(0, 0, 0, 18)
        p.save()
        p.setPen(QPen(sep, 1))
        p.drawLine(0, _TITLEBAR_H - 1, _SPLASH_W, _TITLEBAR_H - 1)
        p.restore()

        # App icon + 'Seeker Accounting', left-aligned
        icon_end_x = 8
        if self._titlebar_icon is not None:
            icon_y = (_TITLEBAR_H - self._titlebar_icon.height()) // 2
            p.drawPixmap(8, icon_y, self._titlebar_icon)
            icon_end_x = 8 + self._titlebar_icon.width() + 6

        p.save()
        font = QFont("Segoe UI", 9)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(_TEXT_COLOR)
        p.drawText(
            QRectF(icon_end_x, 0, _SPLASH_W - icon_end_x - 36, _TITLEBAR_H),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Seeker Accounting",
        )
        p.restore()

    def _paint_particles(self, p: QPainter, elapsed: float) -> None:
        fade_in = min(1.0, elapsed / 0.4)
        fade_out = 1.0
        if elapsed > _TRANSFORM_START:
            t = min(1.0, (elapsed - _TRANSFORM_START) / (_TRANSFORM_END - _TRANSFORM_START))
            fade_out = max(0.05, 1.0 - t * 0.92)

        for pt in self._particles:
            pt.x += pt.dx
            pt.y += pt.dy
            if pt.x < -5:
                pt.x = _SPLASH_W + 5
            elif pt.x > _SPLASH_W + 5:
                pt.x = -5
            if pt.y < -5:
                pt.y = _SPLASH_H + 5
            elif pt.y > _SPLASH_H + 5:
                pt.y = -5

            alpha = int(255 * pt.alpha * fade_in * fade_out)
            if alpha < 1:
                continue
            color = QColor(_BADGE_BLUE)
            color.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(
                int(pt.x - pt.radius), int(pt.y - pt.radius),
                int(pt.radius * 2), int(pt.radius * 2),
            )

    def _paint_symbol(
        self, p: QPainter, elapsed: float,
        cx: float, cy: float, half_size: float, color: QColor,
    ) -> None:
        settle_scale = 1.0
        if _SETTLE_START <= elapsed <= _SETTLE_END:
            st = (elapsed - _SETTLE_START) / (_SETTLE_END - _SETTLE_START)
            settle_scale = 1.0 + 0.018 * math.sin(st * math.pi)

        for piece in self._pieces:
            if elapsed < piece.t_start:
                continue
            duration = piece.t_end - piece.t_start
            t = min(1.0, (elapsed - piece.t_start) / duration)

            if piece.group == _Group.SPINE:
                t_pos = _ease_out_cubic(t)
                t_vis = _ease_out_cubic(min(1.0, t / 0.4))
            elif piece.group == _Group.DIAGONAL:
                t_pos = _ease_out_cubic(t)
                t_vis = _ease_out_cubic(min(1.0, t / 0.4))
            else:
                t_pos = _ease_out_back_soft(t)
                t_vis = _ease_out_cubic(min(1.0, t / 0.35))

            if t_vis < 0.01:
                continue

            offset_x = piece.origin_dx * (1.0 - t_pos)
            offset_y = piece.origin_dy * (1.0 - t_pos)

            scale_x = 1.0
            scale_y = 1.0
            if piece.name == "bar_vertical":
                scale_y = t_pos
                offset_x = 0.0
                offset_y = 0.0

            if piece.group == _Group.DIAGONAL:
                arc = 15.0 * math.sin(t_pos * math.pi) * (1.0 - t_pos)
                if piece.name == "diag_upper_right":
                    offset_x += arc
                    offset_y += arc
                else:
                    offset_x -= arc
                    offset_y -= arc

            if piece.group == _Group.DOT:
                piece_scale = 0.84 + 0.16 * t_pos
            else:
                piece_scale = 0.88 + 0.12 * t_pos

            rotation = piece.start_rotation * (1.0 - t_pos)
            factory = _PATH_FACTORIES[piece.name]
            path = factory(half_size)

            p.save()
            p.setOpacity(t_vis)
            p.translate(cx + offset_x, cy + offset_y)
            p.rotate(rotation)
            p.scale(scale_x * piece_scale * settle_scale, scale_y * piece_scale * settle_scale)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawPath(path)
            p.restore()

    def _badge_progress(self, elapsed: float) -> float:
        if elapsed < _BADGE_START:
            return 0.0
        return min(1.0, (elapsed - _BADGE_START) / (_BADGE_END - _BADGE_START))

    def _transform_progress(self, elapsed: float) -> float:
        if elapsed < _TRANSFORM_START:
            return 0.0
        return min(1.0, (elapsed - _TRANSFORM_START) / (_TRANSFORM_END - _TRANSFORM_START))

    def _current_badge_geometry(self, transform_t: float) -> tuple[float, float, float]:
        t = _ease_in_out_cubic(transform_t)
        cx = _BADGE_SPLASH_CX + (_BADGE_LANDING_CX - _BADGE_SPLASH_CX) * t
        cy = _BADGE_SPLASH_CY + (_BADGE_LANDING_CY - _BADGE_SPLASH_CY) * t
        r = _BADGE_SPLASH_R + (_BADGE_LANDING_R - _BADGE_SPLASH_R) * t
        return cx, cy, r

    def _current_symbol_half_size(self, transform_t: float) -> float:
        t = _ease_in_out_cubic(transform_t)
        splash_hs = _BADGE_SPLASH_R * _SYMBOL_RATIO
        landing_hs = _BADGE_LANDING_R * _SYMBOL_RATIO
        return splash_hs + (landing_hs - splash_hs) * t

    def _current_symbol_color(self, badge_progress: float) -> QColor:
        if badge_progress <= 0.0:
            return QColor(_BADGE_BLUE)
        fill_t = max(0.0, (badge_progress - 0.6) / 0.4)
        return _lerp_color(_BADGE_BLUE, _WHITE, _ease_out_expo(fill_t))

    def _paint_badge_disc(
        self, p: QPainter,
        cx: float, cy: float, r: float, badge_t: float,
    ) -> None:
        ring_end = 0.36
        thicken_end = 0.64

        if badge_t < ring_end:
            t = badge_t / ring_end
            ring_r = r * (0.80 + 0.38 * _ease_out_cubic(t))
            ring_alpha = int(155 * _ease_out_cubic(t))
            ring_width = 2.0 + 1.0 * t
            rotation = 18.0 * t

            color = QColor(_BADGE_BLUE)
            color.setAlpha(ring_alpha)

            p.save()
            p.translate(cx, cy)
            p.rotate(rotation)
            pen = QPen(color, ring_width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(-ring_r, -ring_r, ring_r * 2, ring_r * 2))
            p.restore()

        elif badge_t < thicken_end:
            t = (badge_t - ring_end) / (thicken_end - ring_end)
            t_eased = _ease_out_expo(t)
            ring_width = 3.0 + r * 0.28 * t_eased
            ring_r = r * 1.18
            rotation = 18.0

            color = QColor(_BADGE_BLUE)
            color.setAlpha(int(155 + 60 * t_eased))

            p.save()
            p.translate(cx, cy)
            p.rotate(rotation)
            pen = QPen(color, ring_width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(-ring_r, -ring_r, ring_r * 2, ring_r * 2))
            p.restore()

        else:
            t = (badge_t - thicken_end) / (1.0 - thicken_end)
            t_eased = _ease_out_expo(t)

            fill_alpha = int(255 * t_eased)
            disc_color = QColor(_BADGE_BLUE)
            disc_color.setAlpha(fill_alpha)

            ring_alpha = int(215 + 40 * t_eased)
            ring_color = QColor(_BADGE_BLUE)
            ring_color.setAlpha(ring_alpha)
            ring_width = 3.0 + r * 0.28

            p.save()
            p.translate(cx, cy)
            p.rotate(18.0)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(disc_color))
            p.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

            pen = QPen(ring_color, max(1.5, ring_width * (1.0 - t_eased * 0.7)))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            outer_r = r * (1.18 - 0.18 * t_eased)
            p.drawEllipse(QRectF(-outer_r, -outer_r, outer_r * 2, outer_r * 2))

            p.restore()

    def _paint_glow(
        self, p: QPainter,
        cx: float, cy: float, r: float, badge_t: float,
    ) -> None:
        glow_t = min(1.0, max(0.0, badge_t - 0.9) / 0.1)
        if glow_t <= 0.0:
            return
        glow_r = r * 1.5
        gradient = QRadialGradient(cx, cy, glow_r)
        gc = QColor(_BADGE_GLOW)
        gc.setAlpha(int(18 * glow_t))
        gradient.setColorAt(0.0, gc)
        gc2 = QColor(_BADGE_GLOW)
        gc2.setAlpha(int(8 * glow_t))
        gradient.setColorAt(0.5, gc2)
        gc3 = QColor(_BADGE_GLOW)
        gc3.setAlpha(0)
        gradient.setColorAt(1.0, gc3)

        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))
        p.restore()

    def _paint_message(self, p: QPainter, elapsed: float) -> None:
        if elapsed < _MSG_START or elapsed > _TRANSFORM_END:
            return
        fade_in_dur = 0.22
        if elapsed < _MSG_START + fade_in_dur:
            t = (elapsed - _MSG_START) / fade_in_dur
            opacity = _ease_out_quint(t)
            rise = 10.0 * (1.0 - _ease_out_quint(t))
        elif elapsed < _MSG_END - 0.10:
            opacity = 1.0
            rise = 0.0
        else:
            t_out = min(1.0, (elapsed - (_MSG_END - 0.10)) / 0.35)
            opacity = 1.0 - _ease_in_out_cubic(t_out)
            rise = -6.0 * _ease_in_out_cubic(t_out)

        if opacity < 0.01:
            return

        transform_t = self._transform_progress(elapsed)
        _, badge_cy, badge_r = self._current_badge_geometry(transform_t)
        y = badge_cy + badge_r + 36.0 + rise

        p.save()
        p.setOpacity(opacity)
        p.setFont(self._msg_font)
        p.setPen(QColor(_TEXT_COLOR))
        fm = QFontMetrics(self._msg_font)
        text = "Succeed More."
        text_w = fm.horizontalAdvance(text)
        p.drawText(int((_SPLASH_W - text_w) / 2), int(y), text)
        p.restore()

    def _paint_status(self, p: QPainter, elapsed: float) -> None:
        if not self._status_text:
            return
        opacity = min(0.7, elapsed / 0.5)
        if self._interactive:
            opacity = 0.0
        elif elapsed > _CTA_START:
            fade_t = min(1.0, (elapsed - _CTA_START) / 0.3)
            opacity *= (1.0 - fade_t)

        if opacity < 0.01:
            return
        p.save()
        p.setOpacity(opacity)
        p.setFont(self._status_font)
        p.setPen(_STATUS_COLOR)
        fm = QFontMetrics(self._status_font)
        text_w = fm.horizontalAdvance(self._status_text)
        p.drawText(int((_SPLASH_W - text_w) / 2), int(_STATUS_Y), self._status_text)
        p.restore()
