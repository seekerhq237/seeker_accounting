from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from seeker_accounting.shared.ui.styles.palette import ThemePalette, get_palette
from seeker_accounting.shared.ui.styles.qss_builder import build_stylesheet
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS, ThemeTokens


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, qt_app: QApplication, default_theme: str = "light", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = qt_app
        self._tokens = DEFAULT_TOKENS
        self._current_theme = "light"
        self._current_palette = get_palette("light")
        # Pre-build both theme stylesheets and palettes at startup so every
        # subsequent toggle is a pure dict lookup + setStyleSheet — zero rebuild cost.
        self._stylesheet_cache: dict[str, str] = {}
        self._qpalette_cache: dict[str, QPalette] = {}
        self._prewarm_caches()
        self.apply_theme(default_theme)

    @property
    def current_theme(self) -> str:
        return self._current_theme

    @property
    def current_palette(self) -> ThemePalette:
        return self._current_palette

    @property
    def tokens(self) -> ThemeTokens:
        return self._tokens

    def _prewarm_caches(self) -> None:
        """Build QSS and QPalette for both themes once at startup."""
        for theme_name in ("light", "dark"):
            palette = get_palette(theme_name)
            self._qpalette_cache[theme_name] = self._build_qpalette(palette)
            self._stylesheet_cache[theme_name] = build_stylesheet(palette, self._tokens)

    def apply_theme(self, theme_name: str) -> None:
        normalized = "dark" if theme_name.lower() == "dark" else "light"
        self._current_palette = get_palette(normalized)
        self._current_theme = normalized
        self._app.setPalette(self._qpalette_cache[normalized])
        self._app.setFont(QFont("Segoe UI", self._tokens.typography.size_body))
        self._app.setStyleSheet(self._stylesheet_cache[normalized])
        self.theme_changed.emit(normalized)

    def toggle_theme(self) -> None:
        self.apply_theme("dark" if self._current_theme == "light" else "light")

    def _build_qpalette(self, palette: ThemePalette) -> QPalette:
        qpalette = QPalette()
        qpalette.setColor(QPalette.ColorRole.Window, QColor(palette.app_background))
        qpalette.setColor(QPalette.ColorRole.WindowText, QColor(palette.text_primary))
        qpalette.setColor(QPalette.ColorRole.Base, QColor(palette.workspace_surface))
        qpalette.setColor(QPalette.ColorRole.AlternateBase, QColor(palette.secondary_surface))
        qpalette.setColor(QPalette.ColorRole.Text, QColor(palette.text_primary))
        qpalette.setColor(QPalette.ColorRole.Button, QColor(palette.workspace_surface))
        qpalette.setColor(QPalette.ColorRole.ButtonText, QColor(palette.text_primary))
        qpalette.setColor(QPalette.ColorRole.Highlight, QColor(palette.accent))
        qpalette.setColor(QPalette.ColorRole.HighlightedText, QColor(palette.accent_text))
        qpalette.setColor(QPalette.ColorRole.PlaceholderText, QColor(palette.text_muted))
        return qpalette

