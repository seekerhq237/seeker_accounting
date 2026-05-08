"""StatusChip — compact pill widget for rendering a status label.

A ``StatusChip`` is a small, fixed-height pill containing a colored dot
and a short label. Visual styling (background, border, foreground) is
driven entirely by QSS through the ``#StatusChip`` selector and the
``chipFamily`` dynamic property; the dot color is painted manually using
the active palette so it remains consistent across themes.

Usage::

    chip = StatusChip("posted")          # resolves family via map
    chip.set_status("draft")             # re-resolves and re-applies QSS
    chip = StatusChip("custom", family="warning")  # explicit override

This module is a pure UI primitive — it must not import from ``app/`` or
``modules/`` and contains no business logic.
"""
from __future__ import annotations

from typing import Final

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from seeker_accounting.shared.ui.styles.palette import ThemePalette, get_palette
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

# ──────────────────────────────────────────────────────────────────────
# Semantic status -> family mapping
# ──────────────────────────────────────────────────────────────────────

SEMANTIC_STATUS_MAP: Final[dict[str, str]] = {
    # success family
    "posted": "success", "active": "success", "completed": "success",
    "filed": "success", "paid": "success", "approved": "success",
    "settled": "success", "reconciled": "success", "ready": "success",
    "success": "success", "done": "success", "ok": "success",
    "cleared": "success", "matched": "success", "accepted": "success",
    # accent family (in-progress / draft-ish)
    "draft": "accent", "pending": "accent", "open": "accent",
    "in_progress": "accent", "processing": "accent", "new": "accent",
    "submitted": "accent", "submitted_for_review": "accent",
    "awaiting_approval": "accent", "awaiting_review": "accent",
    # info family
    "info": "info", "scheduled": "info", "planned": "info",
    "fully_depreciated": "info", "calculated": "info", "settling": "info",
    # warning family
    "on_hold": "warning", "hold": "warning", "overdue": "warning",
    "due": "warning", "warning": "warning", "partial": "warning",
    "partially_paid": "warning", "partially_allocated": "warning",
    "unreconciled": "warning", "low_stock": "warning", "unmatched": "warning",
    "needs_review": "warning", "late": "warning", "unpaid": "warning",
    # success family (continued)
    "in_stock": "success",
    # danger family
    "cancelled": "danger", "canceled": "danger", "rejected": "danger",
    "failed": "danger", "error": "danger", "closed": "danger",
    "locked": "danger", "voided": "danger", "void": "danger",
    "blocked": "danger", "invalid": "danger", "expired": "danger",
    # neutral family
    "inactive": "neutral", "archived": "neutral", "disposed": "neutral", "n_a": "neutral",
    "unknown": "neutral", "none": "neutral",
}

DEFAULT_FAMILY: Final[str] = "neutral"

_VALID_FAMILIES: Final[frozenset[str]] = frozenset(
    {"success", "warning", "danger", "info", "neutral", "accent"}
)


def _normalize(status: str) -> str:
    """Lower-case and collapse spaces / dashes into underscores."""
    out = status.strip().lower()
    for ch in (" ", "-"):
        out = out.replace(ch, "_")
    while "__" in out:
        out = out.replace("__", "_")
    return out


def resolve_status_family(status: str | None) -> str:
    """Resolve a status string to one of the six semantic families.

    Unknown / empty / ``None`` values resolve to :data:`DEFAULT_FAMILY`.
    Lookup is case-insensitive and treats spaces / dashes as underscores.
    """
    if not status:
        return DEFAULT_FAMILY
    key = _normalize(status)
    return SEMANTIC_STATUS_MAP.get(key, DEFAULT_FAMILY)


def _format_label(status: str | None) -> str:
    """Produce a human-readable Title Case label for ``status``."""
    if not status:
        return "\u2014"  # em-dash
    cleaned = status.strip().replace("_", " ").replace("-", " ")
    cleaned = " ".join(part for part in cleaned.split() if part)
    if not cleaned:
        return "\u2014"
    return " ".join(word[:1].upper() + word[1:].lower() for word in cleaned.split())


def _active_palette() -> ThemePalette:
    """Best-effort lookup of the currently active :class:`ThemePalette`.

    The :class:`ThemeManager` instance lives on the service registry and is
    not globally accessible from leaf widgets. We infer the active theme
    from the application's :class:`~PySide6.QtGui.QPalette` (Window role
    lightness) which is set by ``ThemeManager.apply_theme`` at startup
    and on every toggle. Falls back to the light palette.
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


# ──────────────────────────────────────────────────────────────────────
# StatusChip widget
# ──────────────────────────────────────────────────────────────────────


class StatusChip(QWidget):
    """Compact pill widget displaying a status with a colored dot + label.

    Object name is ``"StatusChip"`` and the dynamic property
    ``chipFamily`` reflects the resolved family, allowing QSS rules of
    the form ``#StatusChip[chipFamily="success"] { ... }`` to apply
    background / border / foreground colors.
    """

    def __init__(
        self,
        status: str | None = None,
        *,
        family: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StatusChip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        sizes = DEFAULT_TOKENS.sizes
        self.setFixedHeight(sizes.chip_height)

        self._explicit_family: str | None = (
            family if family in _VALID_FAMILIES else None
        )
        self._status: str | None = None
        self._family: str = DEFAULT_FAMILY
        self._label: str = "\u2014"
        self.set_status(status)

    # -- public API -------------------------------------------------------

    def set_status(self, status: str | None) -> None:
        """Update the chip text and re-apply the family-driven QSS."""
        self._status = status
        self._label = _format_label(status)
        if self._explicit_family is not None:
            self._family = self._explicit_family
        else:
            self._family = resolve_status_family(status)

        self.setProperty("chipFamily", self._family)
        # Tooltip preserves the original (non-normalized) status string.
        self.setToolTip(status or "")

        # Force QSS re-evaluation so the new chipFamily takes effect.
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

        self.updateGeometry()
        self.update()

    @property
    def status(self) -> str | None:
        return self._status

    @property
    def family(self) -> str:
        return self._family

    # -- sizing -----------------------------------------------------------

    def sizeHint(self) -> QSize:
        sizes = DEFAULT_TOKENS.sizes
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self._label)
        # padding-left + dot + gap + text + padding-right
        gap = 6
        width = (
            sizes.chip_padding_h
            + sizes.chip_dot_size
            + gap
            + text_w
            + sizes.chip_padding_h
        )
        return QSize(width, sizes.chip_height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # -- paint ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        # Background / border come from QSS — let the styled background
        # render via WA_StyledBackground. We only paint the dot and the
        # label text on top.
        super().paintEvent(event)

        sizes = DEFAULT_TOKENS.sizes
        palette = _active_palette()
        dot_color = QColor(_dot_color(palette, self._family))
        text_color = QColor(_text_color(palette, self._family))

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            rect = self.rect()
            cx_left = rect.left() + sizes.chip_padding_h
            cy = rect.center().y()

            # Dot
            dot_size = sizes.chip_dot_size
            dot_rect = QRect(
                cx_left,
                cy - dot_size // 2,
                dot_size,
                dot_size,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_color)
            painter.drawEllipse(dot_rect)

            # Label
            gap = 6
            text_left = dot_rect.right() + 1 + gap
            text_rect = QRect(
                text_left,
                rect.top(),
                rect.right() - text_left - sizes.chip_padding_h + 1,
                rect.height(),
            )
            painter.setPen(text_color)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._label,
            )
        finally:
            painter.end()


# ──────────────────────────────────────────────────────────────────────
# Palette helpers (shared with the delegate)
# ──────────────────────────────────────────────────────────────────────


def _bg_color(palette: ThemePalette, family: str) -> str:
    return getattr(palette, f"status_{family}_bg", palette.workspace_surface)


def _text_color(palette: ThemePalette, family: str) -> str:
    return getattr(palette, f"status_{family}_fg", palette.text_primary)


def _border_color(palette: ThemePalette, family: str) -> str:
    return getattr(palette, f"status_{family}_border", palette.border_default)


def _dot_color(palette: ThemePalette, family: str) -> str:
    # Dot uses the foreground colour of the family for strong contrast.
    return _text_color(palette, family)
