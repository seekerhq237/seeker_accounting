"""General-purpose theme-aware icon provider (Lucide-based).

Hosts a curated set of inline Lucide SVG glyphs used throughout the shell and
feature surfaces. Icons are colorized against the active `ThemePalette` via a
`currentColor` substitution, cached per (name, state, size, theme).

Phase 1 scope: ships the minimum set required to replace Unicode glyph usage
(menu, chevron-down, search, help-circle, plus, x). Future phases extend the
catalogue without touching call sites.
"""

from __future__ import annotations

from typing import Final, Literal

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from seeker_accounting.shared.ui.styles.palette import ThemePalette
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager

IconState = Literal["normal", "hover", "active", "disabled", "on_accent"]


# Lucide SVG sources (stroke-based, 24x24, uses currentColor for tinting).
# Source: https://lucide.dev — MIT licensed. Paths are inlined to keep the
# icon set declarative and free from filesystem/resource plumbing.
_LUCIDE_SVGS: Final[dict[str, str]] = {
    "menu": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="4" y1="6" x2="20" y2="6"/>'
        '<line x1="4" y1="12" x2="20" y2="12"/>'
        '<line x1="4" y1="18" x2="20" y2="18"/>'
        "</svg>"
    ),
    "chevron_down": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="6 9 12 15 18 9"/>'
        "</svg>"
    ),
    "chevron_right": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="9 6 15 12 9 18"/>'
        "</svg>"
    ),
    "search": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="11" cy="11" r="7"/>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"/>'
        "</svg>"
    ),
    "plus": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="12" y1="5" x2="12" y2="19"/>'
        '<line x1="5" y1="12" x2="19" y2="12"/>'
        "</svg>"
    ),
    "x": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="18" y1="6" x2="6" y2="18"/>'
        '<line x1="6" y1="6" x2="18" y2="18"/>'
        "</svg>"
    ),
    "help_circle": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.8.3-1.5.8-1.5 1.7v.5"/>'
        '<line x1="12" y1="17" x2="12" y2="17.01"/>'
        "</svg>"
    ),
    "bell": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
        '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'
        "</svg>"
    ),
    "sun": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="4"/>'
        '<line x1="12" y1="2" x2="12" y2="4"/>'
        '<line x1="12" y1="20" x2="12" y2="22"/>'
        '<line x1="4.93" y1="4.93" x2="6.34" y2="6.34"/>'
        '<line x1="17.66" y1="17.66" x2="19.07" y2="19.07"/>'
        '<line x1="2" y1="12" x2="4" y2="12"/>'
        '<line x1="20" y1="12" x2="22" y2="12"/>'
        '<line x1="4.93" y1="19.07" x2="6.34" y2="17.66"/>'
        '<line x1="17.66" y1="6.34" x2="19.07" y2="4.93"/>'
        "</svg>"
    ),
    "moon": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
        "</svg>"
    ),
    "refresh": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="23 4 23 10 17 10"/>'
        '<polyline points="1 20 1 14 7 14"/>'
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"/>'
        '<path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14"/>'
        "</svg>"
    ),
    "check": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="20 6 9 17 4 12"/>'
        "</svg>"
    ),
    "star": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 '
        '5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'
        "</svg>"
    ),
    "clock": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="9"/>'
        '<polyline points="12 7 12 12 15 15"/>'
        "</svg>"
    ),
    "layout_grid": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="3" width="7" height="7"/>'
        '<rect x="14" y="3" width="7" height="7"/>'
        '<rect x="3" y="14" width="7" height="7"/>'
        '<rect x="14" y="14" width="7" height="7"/>'
        "</svg>"
    ),
    "building": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="9" width="18" height="13"/>'
        '<path d="M8 22V9"/><path d="M16 22V9"/>'
        '<path d="M3 9l9-7 9 7"/>'
        '<line x1="9" y1="14" x2="9" y2="14.01"/>'
        '<line x1="15" y1="14" x2="15" y2="14.01"/>'
        "</svg>"
    ),
}


class IconProvider:
    """Theme-aware Lucide icon renderer with in-memory pixmap caching."""

    def __init__(self, theme_manager: ThemeManager) -> None:
        self._theme_manager = theme_manager
        self._icon_cache: dict[tuple[str, IconState, int, str], QIcon] = {}
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

    # ── Public API ────────────────────────────────────────────────────

    def icon(
        self,
        name: str,
        *,
        state: IconState = "normal",
        size: int | QSize = 18,
    ) -> QIcon:
        icon_size = size if isinstance(size, int) else max(size.width(), size.height())
        cache_key = (name, state, icon_size, self._theme_manager.current_theme)
        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached
        icon = QIcon(self._render_pixmap(name, state=state, size=icon_size))
        self._icon_cache[cache_key] = icon
        return icon

    def has_icon(self, name: str) -> bool:
        return name in _LUCIDE_SVGS

    def available_icons(self) -> tuple[str, ...]:
        return tuple(_LUCIDE_SVGS.keys())

    def clear_cache(self) -> None:
        self._icon_cache.clear()

    # ── Internals ─────────────────────────────────────────────────────

    def _on_theme_changed(self, _theme_name: str) -> None:
        # Cache is keyed by theme, but prune stale entries to keep memory bounded.
        self._icon_cache.clear()

    def _render_pixmap(self, name: str, *, state: IconState, size: int) -> QPixmap:
        svg_source = _LUCIDE_SVGS.get(name)
        if svg_source is None:
            svg_source = _LUCIDE_SVGS["help_circle"]

        color = self._color_for_state(state, self._theme_manager.current_palette)
        colorized_svg = svg_source.replace(
            "currentColor", color.name(QColor.NameFormat.HexRgb)
        )

        renderer = QSvgRenderer(QByteArray(colorized_svg.encode("utf-8")))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform,
            on=True,
        )
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        return pixmap

    @staticmethod
    def _color_for_state(state: IconState, palette: ThemePalette) -> QColor:
        color_map = {
            "normal": palette.text_secondary,
            "hover": palette.text_primary,
            "active": palette.accent,
            "disabled": palette.disabled_text,
            "on_accent": palette.accent_text,
        }
        return QColor(color_map.get(state, palette.text_secondary))
