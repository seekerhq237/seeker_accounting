from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from PySide6.QtCore import QByteArray, QIODevice, QRectF, QSize, Qt, QFile
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from seeker_accounting.resources import sidebar_icons_rc  # noqa: F401
from seeker_accounting.shared.ui.styles.palette import ThemePalette
from seeker_accounting.shared.ui.styles.theme_manager import ThemeManager

SidebarIconState = Literal["normal", "hover", "active", "disabled"]


@dataclass(frozen=True, slots=True)
class SidebarIconSpec:
    module_key: str
    label: str
    resource_path: str
    concept: str


SIDEBAR_ICON_SPECS: Final[tuple[SidebarIconSpec, ...]] = (
    SidebarIconSpec("dashboard", "Dashboard", ":/icons/sidebar/dashboard.svg", "Overview workspace"),
    SidebarIconSpec("third_parties", "Third Parties", ":/icons/sidebar/third_parties.svg", "Paired entities"),
    SidebarIconSpec("accounting", "Accounting", ":/icons/sidebar/accounting.svg", "Ledger register"),
    SidebarIconSpec("sales", "Sales", ":/icons/sidebar/sales.svg", "Outgoing invoice"),
    SidebarIconSpec("purchases", "Purchases", ":/icons/sidebar/purchases.svg", "Incoming bill"),
    SidebarIconSpec("treasury", "Treasury", ":/icons/sidebar/treasury.svg", "Cash and banking"),
    SidebarIconSpec("inventory", "Inventory", ":/icons/sidebar/inventory.svg", "Stored stock"),
    SidebarIconSpec("fixed_assets", "Fixed Assets", ":/icons/sidebar/fixed_assets.svg", "Capital asset"),
    SidebarIconSpec("projects", "Projects", ":/icons/sidebar/projects.svg", "Structured work board"),
    SidebarIconSpec("payroll", "Payroll", ":/icons/sidebar/payroll.svg", "Payslip and compensation"),
    SidebarIconSpec("reports", "Reports", ":/icons/sidebar/reports.svg", "Charted report"),
    SidebarIconSpec("administration", "Administration", ":/icons/sidebar/administration.svg", "Administrative controls"),
)

_SPEC_BY_MODULE_KEY: Final[dict[str, SidebarIconSpec]] = {
    spec.module_key: spec
    for spec in SIDEBAR_ICON_SPECS
}

_FALLBACK_SVG_TEMPLATE: Final[str] = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <g stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <rect x="5.5" y="5.5" width="13" height="13" rx="2.5"/>
    <path d="M8.5 10.5h7"/>
    <path d="M8.5 14h5"/>
  </g>
</svg>
""".strip()


class SidebarIconProvider:
    """Theme-aware icon renderer for the 12 top-level sidebar modules."""

    def __init__(self, theme_manager: ThemeManager) -> None:
        self._theme_manager = theme_manager
        self._svg_cache: dict[str, str] = {}
        self._icon_cache: dict[tuple[str, SidebarIconState, int, str], QIcon] = {}

    def clear_cache(self) -> None:
        self._icon_cache.clear()

    def spec_for(self, module_key: str) -> SidebarIconSpec | None:
        return _SPEC_BY_MODULE_KEY.get(module_key)

    def icon_for(
        self,
        module_key: str,
        *,
        state: SidebarIconState = "normal",
        size: int | QSize = 18,
    ) -> QIcon:
        icon_size = size if isinstance(size, int) else max(size.width(), size.height())
        cache_key = (
            module_key,
            state,
            icon_size,
            self._theme_manager.current_theme,
        )
        cached_icon = self._icon_cache.get(cache_key)
        if cached_icon is not None:
            return cached_icon

        icon = QIcon(self._render_pixmap(module_key, state=state, size=icon_size))
        self._icon_cache[cache_key] = icon
        return icon

    def _render_pixmap(
        self,
        module_key: str,
        *,
        state: SidebarIconState,
        size: int,
    ) -> QPixmap:
        svg_source = self._load_svg_source(module_key)
        color = self._color_for_state(state, self._theme_manager.current_palette)
        colorized_svg = svg_source.replace("currentColor", color.name(QColor.NameFormat.HexRgb))

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

    def _load_svg_source(self, module_key: str) -> str:
        spec = self.spec_for(module_key)
        resource_path = spec.resource_path if spec is not None else ""
        cached_svg = self._svg_cache.get(resource_path)
        if cached_svg is not None:
            return cached_svg

        if resource_path:
            resource_file = QFile(resource_path)
            if resource_file.exists() and resource_file.open(
                QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text
            ):
                try:
                    svg_source = bytes(resource_file.readAll()).decode("utf-8")
                    self._svg_cache[resource_path] = svg_source
                    return svg_source
                finally:
                    resource_file.close()

        return _FALLBACK_SVG_TEMPLATE

    @staticmethod
    def _color_for_state(state: SidebarIconState, palette: ThemePalette) -> QColor:
        color_map = {
            "normal": palette.text_secondary,
            "hover": palette.text_primary,
            "active": palette.accent,
            "disabled": palette.disabled_text,
        }
        return QColor(color_map.get(state, palette.text_secondary))
