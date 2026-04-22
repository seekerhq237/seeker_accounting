from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ThemeName = Literal["light", "dark"]


@dataclass(frozen=True, slots=True)
class ThemePalette:
    name: ThemeName
    app_background: str
    workspace_surface: str
    secondary_surface: str
    raised_surface: str
    sidebar_surface: str
    sidebar_hover: str
    topbar_surface: str
    border_default: str
    border_strong: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_soft_strong: str
    accent_text: str
    success: str
    warning: str
    danger: str
    info: str
    input_surface: str
    input_border: str
    input_focus: str
    table_header: str
    table_hover: str
    selected_fill: str
    selected_text: str
    disabled_surface: str
    disabled_text: str
    divider_subtle: str


LIGHT_PALETTE = ThemePalette(
    name="light",
    # Operational Desktop: neutral gray base, restrained accent, flat framing.
    app_background="#EDEFF2",
    workspace_surface="#FFFFFF",
    secondary_surface="#F5F6F8",
    raised_surface="#FFFFFF",
    sidebar_surface="#F3F4F7",
    sidebar_hover="#E6E8ED",
    topbar_surface="#F5F6F8",
    border_default="#D6D9DE",
    border_strong="#B9BEC6",
    text_primary="#1B1F24",
    text_secondary="#4A525C",
    text_muted="#747C87",
    accent="#2C5FD4",
    accent_hover="#2553BC",
    accent_soft="#ECF1FB",
    accent_soft_strong="#D5E1F7",
    accent_text="#FFFFFF",
    success="#157347",
    warning="#A15A0F",
    danger="#B42318",
    info="#2553BC",
    input_surface="#FFFFFF",
    input_border="#C8CCD2",
    input_focus="#2C5FD4",
    table_header="#EFF0F3",
    table_hover="#F6F7F9",
    selected_fill="#DCE6F7",
    selected_text="#0F1725",
    disabled_surface="#ECEDF0",
    disabled_text="#8A929C",
    divider_subtle="#E3E5EA",
)

DARK_PALETTE = ThemePalette(
    name="dark",
    # Operational Desktop: cold neutral grays, no blue cast on surfaces.
    app_background="#131821",
    workspace_surface="#1A1F28",
    secondary_surface="#1E242F",
    raised_surface="#20262F",
    sidebar_surface="#141820",
    sidebar_hover="#1F2632",
    topbar_surface="#1A1F28",
    border_default="#2A313D",
    border_strong="#3A4352",
    text_primary="#E7EAEE",
    text_secondary="#B3BAC4",
    text_muted="#7F8895",
    accent="#5A8CF2",
    accent_hover="#4A7DE8",
    accent_soft="#1E2B45",
    accent_soft_strong="#263858",
    accent_text="#F5F7FB",
    success="#2DB27A",
    warning="#D9A54B",
    danger="#E7695A",
    info="#6A9BF3",
    input_surface="#1A1F28",
    input_border="#3A4352",
    input_focus="#5A8CF2",
    table_header="#1E242F",
    table_hover="#222A37",
    selected_fill="#263A5A",
    selected_text="#F0F3F7",
    disabled_surface="#1C222C",
    disabled_text="#6B7380",
    divider_subtle="#222832",
)


def get_palette(theme_name: str) -> ThemePalette:
    return DARK_PALETTE if theme_name.lower() == "dark" else LIGHT_PALETTE

