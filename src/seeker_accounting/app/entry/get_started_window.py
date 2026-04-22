"""
Get Started — a rich multi-page onboarding guide for first-time users.

Shows automatically on the very first launch and is re-accessible at any
time from the ℹ️ help button on the landing screen.

Design: light-themed, paginated carousel with smooth slide transitions,
page indicator dots, and a "Don't show on startup" preference.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Slot,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  Palette (light theme from palette.py)
# ══════════════════════════════════════════════════════════════════════════════

_BG = "#F5F7FB"
_SURFACE = "#FFFFFF"
_RAISED = "#FFFFFF"
_CARD = "#F8FAFD"
_BORDER = "#D9E2EC"
_BORDER_STRONG = "#C5D0DD"
_TEXT = "#182230"
_TEXT_SEC = "#526071"
_TEXT_MUTED = "#7A8797"
_ACCENT = "#2363EA"
_ACCENT_HOVER = "#1B55D1"
_ACCENT_SOFT = "#F3F7FF"
_SUCCESS = "#13795B"
_WARNING = "#B7791F"
_DANGER = "#C53030"
_INFO = "#2563EB"
_DIVIDER = "#E5EBF3"

_FONT_FAMILY = "Segoe UI"

# ── Dimensions ────────────────────────────────────────────────────────────────
_WINDOW_W = 820
_WINDOW_H = 590
_ANIM_DURATION = 320

# ══════════════════════════════════════════════════════════════════════════════
#  Stylesheet
# ══════════════════════════════════════════════════════════════════════════════

_QSS = f"""
QDialog#GetStartedWindow {{
    background: {_BG};
}}
QWidget#PageContainer {{
    background: transparent;
}}

/* Force all labels inside the guide to be transparent */
QDialog#GetStartedWindow QLabel {{
    background: transparent;
}}

/* ── Typography ─────────────────────────────────────────── */
QLabel#GSHeroTitle {{
    color: {_TEXT};
    font-family: "{_FONT_FAMILY}";
    font-size: 28px;
    font-weight: 700;
    letter-spacing: 0.5px;
    background: transparent;
}}
QLabel#GSHeroSubtitle {{
    color: {_TEXT_SEC};
    font-family: "{_FONT_FAMILY}";
    font-size: 15px;
    font-weight: 400;
    background: transparent;
}}
QLabel#GSPageTitle {{
    color: {_TEXT};
    font-family: "{_FONT_FAMILY}";
    font-size: 22px;
    font-weight: 700;
    background: transparent;
}}
QLabel#GSPageSubtitle {{
    color: {_TEXT_SEC};
    font-family: "{_FONT_FAMILY}";
    font-size: 13px;
    font-weight: 400;
    background: transparent;
}}
QLabel#GSSectionTitle {{
    color: {_TEXT};
    font-family: "{_FONT_FAMILY}";
    font-size: 15px;
    font-weight: 600;
    background: transparent;
}}
QLabel#GSBodyText {{
    color: {_TEXT_SEC};
    font-family: "{_FONT_FAMILY}";
    font-size: 13px;
    background: transparent;
}}
QLabel#GSMutedText {{
    color: {_TEXT_MUTED};
    font-family: "{_FONT_FAMILY}";
    font-size: 12px;
    background: transparent;
}}

/* ── Cards ──────────────────────────────────────────────── */
QFrame#GSCard {{
    background: {_SURFACE};
    border: 1px solid {_BORDER};
    border-radius: 10px;
    padding: 14px;
}}
QFrame#GSCardAccent {{
    background: {_ACCENT_SOFT};
    border: 1px solid {_ACCENT};
    border-radius: 10px;
    padding: 14px;
}}
QFrame#GSStepCard {{
    background: {_SURFACE};
    border: 1px solid {_BORDER};
    border-radius: 12px;
    padding: 16px 18px;
}}
QFrame#GSFeatureCard {{
    background: {_CARD};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 12px;
}}

/* ── Buttons ────────────────────────────────────────────── */
QPushButton#GSPrimaryBtn {{
    background: {_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 8px 24px;
    font-family: "{_FONT_FAMILY}";
    font-size: 13px;
    font-weight: 600;
    min-height: 34px;
}}
QPushButton#GSPrimaryBtn:hover {{
    background: {_ACCENT_HOVER};
}}
QPushButton#GSSecondaryBtn {{
    background: transparent;
    color: {_TEXT_SEC};
    border: 1px solid {_BORDER_STRONG};
    border-radius: 6px;
    padding: 8px 20px;
    font-family: "{_FONT_FAMILY}";
    font-size: 13px;
    font-weight: 500;
    min-height: 34px;
}}
QPushButton#GSSecondaryBtn:hover {{
    background: {_CARD};
    color: {_TEXT};
    border-color: {_ACCENT};
}}
QPushButton#GSGhostBtn {{
    background: transparent;
    color: {_TEXT_MUTED};
    border: none;
    padding: 4px 12px;
    font-family: "{_FONT_FAMILY}";
    font-size: 12px;
}}
QPushButton#GSGhostBtn:hover {{
    color: {_TEXT};
}}
QPushButton#GSActionBtn {{
    background: {_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 12px 32px;
    font-family: "{_FONT_FAMILY}";
    font-size: 14px;
    font-weight: 600;
    min-height: 40px;
}}
QPushButton#GSActionBtn:hover {{
    background: {_ACCENT_HOVER};
}}
QPushButton#GSActionBtnSecondary {{
    background: transparent;
    color: {_TEXT_SEC};
    border: 1px solid {_BORDER_STRONG};
    border-radius: 8px;
    padding: 12px 32px;
    font-family: "{_FONT_FAMILY}";
    font-size: 14px;
    font-weight: 500;
    min-height: 40px;
}}
QPushButton#GSActionBtnSecondary:hover {{
    background: {_CARD};
    color: {_TEXT};
    border-color: {_ACCENT};
}}

/* ── Shortcuts table ────────────────────────────────────── */
QFrame#GSShortcutRow {{
    background: {_SURFACE};
    border: none;
    border-bottom: 1px solid {_DIVIDER};
    padding: 6px 12px;
}}
QLabel#GSKeyBadge {{
    background: {_CARD};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 2px 8px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    font-weight: 600;
}}

/* ── Checkbox ───────────────────────────────────────────── */
QCheckBox#GSDontShowCheck {{
    color: {_TEXT_MUTED};
    font-family: "{_FONT_FAMILY}";
    font-size: 12px;
    spacing: 6px;
}}

/* ── Nav module item ─────────────────────────────────────── */
QFrame#GSNavItem {{
    background: {_SURFACE};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px 10px;
}}

/* ── Scroll area ────────────────────────────────────────── */
QScrollArea#GSScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea#GSScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollArea#GSScrollArea QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px 1px;
}}
QScrollArea#GSScrollArea QScrollBar::handle:vertical {{
    background: {_BORDER_STRONG};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollArea#GSScrollArea QScrollBar::handle:vertical:hover {{
    background: {_TEXT_MUTED};
}}
QScrollArea#GSScrollArea QScrollBar::add-line:vertical,
QScrollArea#GSScrollArea QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollArea#GSScrollArea QScrollBar::add-page:vertical,
QScrollArea#GSScrollArea QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* ── Divider ─────────────────────────────────────────────── */
QFrame#GSDivider {{
    background: {_DIVIDER};
    max-height: 1px;
    min-height: 1px;
}}
"""


# ══════════════════════════════════════════════════════════════════════════════
#  Small reusable builders
# ══════════════════════════════════════════════════════════════════════════════

def _label(text: str, object_name: str, *, wrap: bool = False, align: Qt.AlignmentFlag | None = None) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def _icon_label(emoji: str, size: int = 32) -> QLabel:
    lbl = QLabel(emoji)
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(f"font-size: {size - 4}px; background: transparent; border: none;")
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setObjectName("GSDivider")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


def _card(object_name: str = "GSCard") -> QFrame:
    f = QFrame()
    f.setObjectName(object_name)
    return f


def _step_card(number: str, icon: str, title: str, desc: str) -> QFrame:
    """Numbered step card for the setup flow page."""
    frame = _card("GSStepCard")
    hl = QHBoxLayout(frame)
    hl.setContentsMargins(14, 12, 14, 12)
    hl.setSpacing(14)

    # Number badge
    badge = QLabel(number)
    badge.setFixedSize(36, 36)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"background: {_ACCENT}; color: #FFFFFF; border-radius: 18px; "
        f'font-family: "{_FONT_FAMILY}"; font-size: 16px; font-weight: 700;'
    )
    hl.addWidget(badge)

    # Icon
    hl.addWidget(_icon_label(icon, 34))

    # Text
    text_col = QVBoxLayout()
    text_col.setSpacing(2)
    text_col.addWidget(_label(title, "GSSectionTitle"))
    text_col.addWidget(_label(desc, "GSBodyText", wrap=True))
    hl.addLayout(text_col, 1)

    return frame


def _feature_tile(icon: str, title: str, color: str) -> QFrame:
    """Small tile for the features grid."""
    frame = _card("GSFeatureCard")
    vl = QVBoxLayout(frame)
    vl.setContentsMargins(8, 10, 8, 10)
    vl.setSpacing(4)
    vl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    icon_lbl = QLabel(icon)
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_lbl.setFixedHeight(28)
    icon_lbl.setStyleSheet(
        f"font-size: 20px; background: transparent; border: none;"
    )
    vl.addWidget(icon_lbl)

    title_lbl = QLabel(title.replace("\n", " "))
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_lbl.setWordWrap(True)
    title_lbl.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Preferred,
    )
    title_lbl.setStyleSheet(
        f"color: {color}; font-family: \"{_FONT_FAMILY}\"; font-size: 11px; "
        f"font-weight: 600; background: transparent; border: none;"
    )
    vl.addWidget(title_lbl)
    # No fixed height — tile grows to fit text content
    frame.setMinimumHeight(76)
    return frame


def _shortcut_row(keys: str, description: str) -> QFrame:
    """Single row in the shortcuts table."""
    frame = QFrame()
    frame.setObjectName("GSShortcutRow")
    hl = QHBoxLayout(frame)
    hl.setContentsMargins(12, 6, 12, 6)
    hl.setSpacing(12)

    badge = QLabel(keys)
    badge.setObjectName("GSKeyBadge")
    badge.setFixedWidth(140)
    hl.addWidget(badge)

    desc_lbl = _label(description, "GSBodyText")
    hl.addWidget(desc_lbl, 1)
    return frame


def _nav_module_item(icon: str, name: str, desc: str) -> QFrame:
    """Sidebar module preview item."""
    frame = QFrame()
    frame.setObjectName("GSNavItem")
    hl = QHBoxLayout(frame)
    hl.setContentsMargins(8, 5, 8, 5)
    hl.setSpacing(10)

    hl.addWidget(_icon_label(icon, 22))

    text_col = QVBoxLayout()
    text_col.setSpacing(0)
    name_lbl = QLabel(name)
    name_lbl.setStyleSheet(
        f"color: {_TEXT}; font-family: \"{_FONT_FAMILY}\"; font-size: 12px; "
        f"font-weight: 600; background: transparent;"
    )
    text_col.addWidget(name_lbl)
    desc_lbl = QLabel(desc)
    desc_lbl.setStyleSheet(
        f"color: {_TEXT_MUTED}; font-family: \"{_FONT_FAMILY}\"; font-size: 10px; "
        f"background: transparent;"
    )
    desc_lbl.setWordWrap(True)
    text_col.addWidget(desc_lbl)
    hl.addLayout(text_col, 1)
    return frame


def _scroll_page(content: QWidget) -> QScrollArea:
    """Wrap a content widget in a styled scroll area for a page."""
    sa = QScrollArea()
    sa.setObjectName("GSScrollArea")
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(content)
    return sa


# ══════════════════════════════════════════════════════════════════════════════
#  Page indicator dot
# ══════════════════════════════════════════════════════════════════════════════

class _PageDot(QWidget):
    """Tiny circle. Active = accent, inactive = muted border."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self.setFixedSize(10, 10)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._active:
            p.setBrush(QColor(_ACCENT))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(QColor(_BORDER_STRONG))
            p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 8, 8)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  Main window
# ══════════════════════════════════════════════════════════════════════════════

class GetStartedWindow(QDialog):
    """Six-page onboarding carousel."""

    #: Possible values returned by chosen_action after the dialog closes.
    ACTION_NONE = ""
    ACTION_LOGIN = "login"
    ACTION_CREATE_ORG = "create_org"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GetStartedWindow")
        self.setWindowTitle("Get Started — Seeker Accounting")
        self.setFixedSize(_WINDOW_W, _WINDOW_H)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(_QSS)

        self._dont_show = False
        self._animating = False
        self._chosen_action: str = self.ACTION_NONE

        self._pages: list[QWidget] = []
        self._dots: list[_PageDot] = []

        self._build_ui()
        self._go_to_page(0, animate=False)

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.setObjectName("PageContainer")

        self._pages = [
            self._build_page_welcome(),
            self._build_page_setup(),
            self._build_page_navigation(),
            self._build_page_features(),
            self._build_page_shortcuts(),
            self._build_page_ready(),
        ]
        for page in self._pages:
            self._stack.addWidget(page)

        root.addWidget(self._stack, 1)

        # Bottom bar: dots + buttons
        bottom = QFrame()
        bottom.setStyleSheet(f"background: {_CARD}; border-top: 1px solid {_DIVIDER};")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(24, 10, 24, 10)
        bl.setSpacing(12)

        # Skip / Back
        self._btn_skip = QPushButton("Skip")
        self._btn_skip.setObjectName("GSGhostBtn")
        self._btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_skip.setStyleSheet(
            f'QPushButton {{ background: transparent; color: {_TEXT_MUTED}; border: none;'
            f' padding: 4px 12px; font-family: "{_FONT_FAMILY}"; font-size: 12px; }}'
            f' QPushButton:hover {{ color: {_TEXT}; }}'
        )
        self._btn_skip.clicked.connect(self._on_skip)
        bl.addWidget(self._btn_skip)

        self._btn_back = QPushButton("Back")
        self._btn_back.setObjectName("GSSecondaryBtn")
        self._btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_back.setStyleSheet(
            f'QPushButton {{ background: transparent; color: {_TEXT_SEC};'
            f' border: 1px solid {_BORDER_STRONG}; border-radius: 6px;'
            f' padding: 8px 20px; font-family: "{_FONT_FAMILY}"; font-size: 13px;'
            f' font-weight: 500; min-height: 34px; }}'
            f' QPushButton:hover {{ background: {_CARD}; color: {_TEXT}; border-color: {_ACCENT}; }}'
        )
        self._btn_back.clicked.connect(self._on_back)
        bl.addWidget(self._btn_back)

        bl.addStretch(1)

        # Page dots
        dots_row = QHBoxLayout()
        dots_row.setSpacing(8)
        for _ in self._pages:
            dot = _PageDot()
            dots_row.addWidget(dot)
            self._dots.append(dot)
        bl.addLayout(dots_row)

        bl.addStretch(1)

        # Next / Finish
        self._btn_next = QPushButton("Next")
        self._btn_next.setObjectName("GSPrimaryBtn")
        self._btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_next.setStyleSheet(
            f'QPushButton {{ background: {_ACCENT}; color: #FFFFFF; border: none;'
            f' border-radius: 6px; padding: 8px 24px; font-family: "{_FONT_FAMILY}";'
            f' font-size: 13px; font-weight: 600; min-height: 34px; }}'
            f' QPushButton:hover {{ background: {_ACCENT_HOVER}; }}'
        )
        self._btn_next.clicked.connect(self._on_next)
        bl.addWidget(self._btn_next)

        root.addWidget(bottom)

    # ══════════════════════════════════════════════════════════════════
    #  PAGE BUILDERS
    # ══════════════════════════════════════════════════════════════════

    # ── Page 1: Welcome ───────────────────────────────────────────────

    def _build_page_welcome(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageContainer")
        vl = QVBoxLayout(page)
        vl.setContentsMargins(48, 36, 48, 20)
        vl.setSpacing(0)

        vl.addStretch(2)

        # Emoji hero
        hero_icon = QLabel("\U0001f4ca")  # 📊
        hero_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_icon.setStyleSheet("font-size: 56px; background: transparent;")
        vl.addWidget(hero_icon)

        vl.addSpacing(16)

        title = _label("Welcome to Seeker Accounting", "GSHeroTitle", align=Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(title)

        vl.addSpacing(12)

        subtitle = _label(
            "A professional desktop accounting system built for growing businesses.\n"
            "Multi-company, OHADA-ready, with complete financial management\n"
            "from chart of accounts to payroll.",
            "GSHeroSubtitle",
            wrap=True,
            align=Qt.AlignmentFlag.AlignCenter,
        )
        vl.addWidget(subtitle)

        vl.addSpacing(24)

        # Highlight badges
        badges = QHBoxLayout()
        badges.setSpacing(8)
        badges.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for icon, text, color in [
            ("\u2705", "Double-Entry", _SUCCESS),
            ("\U0001f3e2", "Multi-Company", _ACCENT),
            ("\U0001f30d", "OHADA-Ready", _INFO),
            ("\U0001f512", "Secure & Auditable", _WARNING),
        ]:
            badge_frame = QFrame()
            badge_frame.setStyleSheet(
                f"background: {_SURFACE}; border: 1px solid {_BORDER}; border-radius: 14px;"
            )
            bhl = QHBoxLayout(badge_frame)
            bhl.setContentsMargins(8, 4, 8, 4)
            bhl.setSpacing(4)
            bhl.addWidget(_icon_label(icon, 14))
            badge_text = QLabel(text)
            badge_text.setStyleSheet(
                f"color: {color}; font-family: \"{_FONT_FAMILY}\"; font-size: 11px; "
                f"font-weight: 600; background: transparent; border: none;"
            )
            bhl.addWidget(badge_text)
            badges.addWidget(badge_frame)

        vl.addLayout(badges)

        vl.addStretch(3)

        hint = _label(
            "This quick guide will show you how to get the most out of Seeker Accounting.",
            "GSMutedText",
            align=Qt.AlignmentFlag.AlignCenter,
        )
        vl.addWidget(hint)

        return page

    # ── Page 2: First-Time Setup ──────────────────────────────────────

    def _build_page_setup(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageContainer")
        vl = QVBoxLayout(page)
        vl.setContentsMargins(40, 28, 40, 16)
        vl.setSpacing(0)

        vl.addWidget(_label("\U0001f680  Your First Steps", "GSPageTitle"))
        vl.addSpacing(4)
        vl.addWidget(_label(
            "Follow these steps to set up your first organisation and start working.",
            "GSPageSubtitle",
            wrap=True,
        ))
        vl.addSpacing(16)

        # Step cards
        vl.addWidget(_step_card(
            "1", "\U0001f3e2",
            "Create an Organisation",
            "Click 'Create Organisation' on the landing screen. Enter the company name, "
            "country, and currency. An admin user will be generated automatically.",
        ))
        vl.addSpacing(8)
        vl.addWidget(_step_card(
            "2", "\U0001f4d1",
            "Import Chart of Accounts",
            "During setup you'll be offered to import an OHADA chart template (or skip). "
            "This seeds your general ledger with a full account hierarchy.",
        ))
        vl.addSpacing(8)
        vl.addWidget(_step_card(
            "3", "\U0001f4c5",
            "Set Up a Fiscal Year",
            "Define your accounting fiscal year and generate monthly (or custom) periods. "
            "Periods control when transactions can be posted or locked.",
        ))

        vl.addSpacing(16)
        vl.addWidget(_divider())
        vl.addSpacing(10)

        # Extra tips
        tips_row = QHBoxLayout()
        tips_row.setSpacing(12)

        tip1 = _card("GSCard")
        t1l = QVBoxLayout(tip1)
        t1l.setSpacing(4)
        t1l.addWidget(_icon_label("\U0001f511", 20))
        t1l.addWidget(_label("License Activation", "GSSectionTitle"))
        t1l.addWidget(_label(
            "Activate from the landing screen using the key icon (🔑) — no login required.",
            "GSBodyText", wrap=True,
        ))
        tips_row.addWidget(tip1)

        tip2 = _card("GSCard")
        t2l = QVBoxLayout(tip2)
        t2l.setSpacing(4)
        t2l.addWidget(_icon_label("\U0001f527", 20))
        t2l.addWidget(_label("System Admin", "GSSectionTitle"))
        t2l.addWidget(_label(
            "Access the system admin console from the wrench icon (🔧) on the landing screen.",
            "GSBodyText", wrap=True,
        ))
        tips_row.addWidget(tip2)

        vl.addLayout(tips_row)

        return _scroll_page(page)

    # ── Page 3: Navigation Tour ───────────────────────────────────────

    def _build_page_navigation(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageContainer")
        vl = QVBoxLayout(page)
        vl.setContentsMargins(40, 28, 40, 16)
        vl.setSpacing(0)

        vl.addWidget(_label("\U0001f9ed  Navigation Overview", "GSPageTitle"))
        vl.addSpacing(4)
        vl.addWidget(_label(
            "Your workspace has a sidebar on the left with collapsible module groups, "
            "a context-rich top bar, and a central content area.",
            "GSPageSubtitle", wrap=True,
        ))
        vl.addSpacing(14)

        # Two-column: left sidebar mockup, right description
        cols = QHBoxLayout()
        cols.setSpacing(16)

        # Left column — nav modules
        nav_col = QVBoxLayout()
        nav_col.setSpacing(5)

        modules = [
            ("\U0001f3e0", "Home", "Dashboard with KPIs and quick actions"),
            ("\U0001f465", "Third Parties", "Customers and suppliers management"),
            ("\U0001f4d2", "Accounting", "Chart of accounts, journals, fiscal periods, tax codes"),
            ("\U0001f4b0", "Sales", "Sales invoices and customer receipts"),
            ("\U0001f6d2", "Purchases", "Purchase bills and supplier payments"),
            ("\U0001f3e6", "Treasury", "Cash & bank accounts, reconciliation"),
            ("\U0001f4e6", "Inventory", "Items, stock movements, warehouses"),
            ("\U0001f3d7\ufe0f", "Fixed Assets", "Asset register, depreciation runs"),
            ("\U0001f4b5", "Payroll", "Salary calculation, payslips, accounting"),
            ("\U0001f4ca", "Reports", "Financial statements and analysis"),
            ("\u2699\ufe0f", "Administration", "Users, roles, audit log, settings"),
        ]

        for icon, name, desc in modules:
            nav_col.addWidget(_nav_module_item(icon, name, desc))

        cols.addLayout(nav_col, 3)

        # Right column — layout description
        desc_col = QVBoxLayout()
        desc_col.setSpacing(12)

        layout_card = _card("GSCardAccent")
        lcl = QVBoxLayout(layout_card)
        lcl.setSpacing(8)
        lcl.addWidget(_label("Workspace Layout", "GSSectionTitle"))

        for icon, text in [
            ("\u25c0", "Sidebar — collapse/expand module groups"),
            ("\u25b2", "Top bar — company switcher, user profile, theme toggle"),
            ("\u25fc", "Content area — tables, forms, and document workspaces"),
            ("\U0001f4ac", "Dialogs — create/edit flows open in focused dialogs"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_icon_label(icon, 16))
            row.addWidget(_label(text, "GSBodyText", wrap=True), 1)
            lcl.addLayout(row)

        desc_col.addWidget(layout_card)
        desc_col.addStretch(1)

        cols.addLayout(desc_col, 2)

        vl.addLayout(cols, 1)
        return _scroll_page(page)

    # ── Page 4: Key Features ──────────────────────────────────────────

    def _build_page_features(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageContainer")
        vl = QVBoxLayout(page)
        vl.setContentsMargins(28, 20, 28, 10)
        vl.setSpacing(0)

        vl.addWidget(_label("\u2728  Key Features", "GSPageTitle"))
        vl.addSpacing(4)
        vl.addWidget(_label(
            "Seeker Accounting covers the full accounting lifecycle — "
            "from chart setup to financial reporting.",
            "GSPageSubtitle", wrap=True,
        ))
        vl.addSpacing(16)

        features = [
            ("\U0001f4d0", "Double-Entry\nAccounting", _ACCENT),
            ("\U0001f3e2", "Multi-Company\nSupport", _INFO),
            ("\U0001f30d", "OHADA\nCompliance", _SUCCESS),
            ("\U0001f4c5", "Fiscal Period\nControl", _WARNING),
            ("\U0001f4d3", "Journal\nEntries", _ACCENT),
            ("\U0001f465", "Customer &\nSupplier Mgmt", _INFO),
            ("\U0001f4b0", "Sales &\nPurchases", _SUCCESS),
            ("\U0001f3e6", "Cash & Bank\nManagement", _WARNING),
            ("\U0001f4e6", "Inventory\nTracking", _ACCENT),
            ("\U0001f3d7\ufe0f", "Fixed Asset\nDepreciation", _INFO),
            ("\U0001f4b5", "Payroll\nProcessing", _SUCCESS),
            ("\U0001f4ca", "Financial\nReporting", _DANGER),
        ]

        # 3 rows of 4
        for row_start in range(0, len(features), 4):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)
            for icon, title, color in features[row_start:row_start + 4]:
                row_layout.addWidget(_feature_tile(icon, title, color))
            vl.addLayout(row_layout)
            vl.addSpacing(6)

        vl.addSpacing(4)

        vl.addWidget(_label(
            "All features follow strict double-entry accounting rules with period-controlled posting.",
            "GSMutedText",
            align=Qt.AlignmentFlag.AlignCenter,
        ))

        return _scroll_page(page)

    # ── Page 5: Shortcuts & Tips ──────────────────────────────────────

    def _build_page_shortcuts(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageContainer")
        vl = QVBoxLayout(page)
        vl.setContentsMargins(40, 28, 40, 16)
        vl.setSpacing(0)

        vl.addWidget(_label("\u26a1  Tips & Shortcuts", "GSPageTitle"))
        vl.addSpacing(4)
        vl.addWidget(_label(
            "Power-user features to help you work faster.",
            "GSPageSubtitle", wrap=True,
        ))
        vl.addSpacing(16)

        # Shortcuts table
        shortcuts_card = _card("GSCard")
        scl = QVBoxLayout(shortcuts_card)
        scl.setContentsMargins(0, 0, 0, 0)
        scl.setSpacing(0)

        shortcuts = [
            ("Ctrl + K", "Open Command Palette — search and run actions"),
            ("Ctrl + F", "Quick Search — find records across the active module"),
            ("Ctrl + N", "New Record — create a new item in the current page"),
            ("Ctrl + Shift + T", "Toggle Theme — switch between light and dark mode"),
            ("F5", "Refresh — reload the current page data"),
            ("Escape", "Close Dialog — dismiss the active dialog or overlay"),
        ]
        for keys, desc in shortcuts:
            scl.addWidget(_shortcut_row(keys, desc))

        vl.addWidget(shortcuts_card)

        vl.addSpacing(16)

        # Pro tips
        vl.addWidget(_label("Pro Tips", "GSSectionTitle"))
        vl.addSpacing(8)

        tips = [
            ("\U0001f4a1", "Post with Control",
             "Documents start as drafts. Posting is always a deliberate action — "
             "posted entries become immutable and balance the ledger."),
            ("\U0001f512", "Period Locking",
             "Close fiscal periods to prevent accidental changes to historical data. "
             "Locked periods block all posting operations."),
            ("\U0001f4be", "Organisation Settings",
             "Configure company defaults, currency, and preferences from "
             "Administration → Organisation Settings after logging in."),
        ]
        for icon, title, desc in tips:
            tip_row = QHBoxLayout()
            tip_row.setSpacing(10)
            tip_row.addWidget(_icon_label(icon, 22))
            tip_col = QVBoxLayout()
            tip_col.setSpacing(1)
            tip_col.addWidget(_label(title, "GSSectionTitle"))
            tip_col.addWidget(_label(desc, "GSBodyText", wrap=True))
            tip_row.addLayout(tip_col, 1)
            vl.addLayout(tip_row)
            vl.addSpacing(6)

        return _scroll_page(page)

    # ── Page 6: Ready! ────────────────────────────────────────────────

    def _build_page_ready(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PageContainer")
        vl = QVBoxLayout(page)
        vl.setContentsMargins(48, 36, 48, 24)
        vl.setSpacing(0)

        vl.addStretch(2)

        # Celebratory icon
        icon = QLabel("\U0001f389")  # 🎉
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 52px; background: transparent;")
        vl.addWidget(icon)
        vl.addSpacing(14)

        vl.addWidget(_label(
            "You're All Set!",
            "GSHeroTitle",
            align=Qt.AlignmentFlag.AlignCenter,
        ))
        vl.addSpacing(10)
        vl.addWidget(_label(
            "You now know the essentials of Seeker Accounting.\n"
            "Create your first organisation or log in to an existing one to get started.",
            "GSHeroSubtitle",
            wrap=True,
            align=Qt.AlignmentFlag.AlignCenter,
        ))

        vl.addSpacing(28)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_login = QPushButton("LOG IN")
        btn_login.setObjectName("GSActionBtn")
        btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_login.setFixedWidth(180)
        btn_login.clicked.connect(self._on_login_clicked)
        btn_row.addWidget(btn_login)

        btn_create = QPushButton("Create Organisation")
        btn_create.setObjectName("GSActionBtnSecondary")
        btn_create.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_create.setFixedWidth(200)
        btn_create.clicked.connect(self._on_create_org_clicked)
        btn_row.addWidget(btn_create)

        vl.addLayout(btn_row)

        vl.addStretch(3)

        # "Don't show on startup" checkbox
        self._dont_show_check = QCheckBox("Don't show this guide on startup")
        self._dont_show_check.setObjectName("GSDontShowCheck")
        self._dont_show_check.toggled.connect(self._on_dont_show_toggled)
        vl.addWidget(self._dont_show_check, alignment=Qt.AlignmentFlag.AlignCenter)

        vl.addSpacing(4)
        vl.addWidget(_label(
            "You can always reopen this guide from the  ℹ️  button on the landing screen.",
            "GSMutedText",
            align=Qt.AlignmentFlag.AlignCenter,
        ))

        return page

    # ══════════════════════════════════════════════════════════════════
    #  Navigation
    # ══════════════════════════════════════════════════════════════════

    def _current_index(self) -> int:
        return self._stack.currentIndex()

    def _go_to_page(self, index: int, *, animate: bool = True) -> None:
        if index < 0 or index >= len(self._pages):
            return
        if self._animating:
            return

        old_index = self._stack.currentIndex()

        # Update dots
        for i, dot in enumerate(self._dots):
            dot.set_active(i == index)

        # Update buttons
        self._btn_back.setVisible(index > 0)
        self._btn_skip.setVisible(index < len(self._pages) - 1)
        is_last = index == len(self._pages) - 1
        self._btn_next.setText("Get Started" if is_last else "Next")

        if not animate or old_index == index:
            self._stack.setCurrentIndex(index)
            return

        # ── Slide animation ───────────────────────────────────────────
        direction = 1 if index > old_index else -1
        width = self._stack.width()

        old_page = self._pages[old_index]
        new_page = self._pages[index]

        # Position new page off-screen
        new_page.setGeometry(
            direction * width, 0, width, self._stack.height()
        )
        self._stack.setCurrentIndex(index)
        new_page.show()
        old_page.show()
        old_page.raise_()
        new_page.raise_()

        self._animating = True

        group = QParallelAnimationGroup(self)

        # Slide old page out
        anim_old = QPropertyAnimation(old_page, b"pos")
        anim_old.setDuration(_ANIM_DURATION)
        anim_old.setStartValue(QPoint(0, 0))
        anim_old.setEndValue(QPoint(-direction * width, 0))
        anim_old.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(anim_old)

        # Slide new page in
        anim_new = QPropertyAnimation(new_page, b"pos")
        anim_new.setDuration(_ANIM_DURATION)
        anim_new.setStartValue(QPoint(direction * width, 0))
        anim_new.setEndValue(QPoint(0, 0))
        anim_new.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(anim_new)

        group.finished.connect(lambda: self._on_anim_finished(old_page))
        group.start()

    def _on_anim_finished(self, old_page: QWidget) -> None:
        self._animating = False
        old_page.hide()

    # ── Button handlers ───────────────────────────────────────────────

    @Slot()
    def _on_login_clicked(self) -> None:
        self._chosen_action = self.ACTION_LOGIN
        self.accept()

    @Slot()
    def _on_create_org_clicked(self) -> None:
        self._chosen_action = self.ACTION_CREATE_ORG
        self.accept()

    @Slot()
    def _on_next(self) -> None:
        idx = self._current_index()
        if idx >= len(self._pages) - 1:
            self.accept()
        else:
            self._go_to_page(idx + 1)

    @Slot()
    def _on_back(self) -> None:
        self._go_to_page(self._current_index() - 1)

    @Slot()
    def _on_skip(self) -> None:
        self.accept()

    @Slot()
    def _on_dont_show_toggled(self, checked: bool) -> None:
        self._dont_show = checked

    # ── Public API ────────────────────────────────────────────────────

    @property
    def dont_show_on_startup(self) -> bool:
        return self._dont_show

    @property
    def chosen_action(self) -> str:
        """The action chosen on the final page (ACTION_LOGIN, ACTION_CREATE_ORG, or ACTION_NONE)."""
        return self._chosen_action

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        # Center on parent or screen
        parent = self.parentWidget()
        if parent is not None:
            geo = parent.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen()
            if screen is not None:
                sg = screen.availableGeometry()
                self.move(
                    sg.x() + (sg.width() - self.width()) // 2,
                    sg.y() + (sg.height() - self.height()) // 2,
                )

    # ── Class-level convenience ───────────────────────────────────────

    @classmethod
    def show_guide(cls, parent: QWidget | None = None) -> tuple[bool, str]:
        """Show the guide unconditionally.

        Returns ``(dont_show_on_startup, chosen_action)`` where ``chosen_action``
        is one of the ACTION_* class constants.
        """
        dlg = cls(parent)
        dlg.exec()
        return dlg.dont_show_on_startup, dlg.chosen_action

    @classmethod
    def show_if_first_launch(
        cls,
        config_dir: Path,
        parent: QWidget | None = None,
    ) -> str:
        """Show guide on startup unless user opted out via the checkbox.

        Returns the chosen action constant (ACTION_LOGIN, ACTION_CREATE_ORG, or
        ACTION_NONE), or ACTION_NONE when the guide was skipped because the user
        has already seen it.
        """
        from seeker_accounting.config.app_state import has_seen_get_started, mark_get_started_seen

        if has_seen_get_started(config_dir):
            return cls.ACTION_NONE

        dlg = cls(parent)
        dlg.exec()

        if dlg.dont_show_on_startup:
            mark_get_started_seen(config_dir)

        return dlg.chosen_action
