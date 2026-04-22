from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TypographyTokens:
    family_primary: str = "Segoe UI"
    size_app_title: int = 18
    size_section_title: int = 13
    size_card_title: int = 12
    size_landing_wordmark: int = 50
    size_landing_tagline: int = 13
    size_body: int = 11
    size_small: int = 10
    size_dense: int = 10
    size_caption: int = 10
    weight_regular: int = 400
    weight_medium: int = 500
    weight_semibold: int = 600


@dataclass(frozen=True, slots=True)
class SpacingTokens:
    page_padding: int = 20
    section_gap: int = 16
    compact_gap: int = 8
    control_gap: int = 10
    sidebar_padding: int = 16
    window_padding: int = 56
    landing_panel_padding: int = 48
    landing_footer_padding: int = 20
    landing_panel_gap: int = 32


@dataclass(frozen=True, slots=True)
class RadiusTokens:
    # Operational Desktop: aggressively low radii on primary work surfaces.
    # Entry-point screens (splash, get-started hero) keep their own hardcoded radii.
    small: int = 2
    medium: int = 4
    large: int = 6
    xlarge: int = 8


@dataclass(frozen=True, slots=True)
class SizeTokens:
    sidebar_width: int = 172
    sidebar_collapsed_width: int = 44
    sidebar_parent_height: int = 24
    sidebar_child_height: int = 22
    sidebar_icon_size: int = 14
    sidebar_animation_ms: int = 120
    topbar_height: int = 36
    topbar_control_height: int = 26
    control_height: int = 22
    button_height: int = 22
    row_height: int = 22
    nav_button_height: int = 26
    topbar_search_width: int = 420
    topbar_company_width: int = 160
    topbar_fiscal_width: int = 132
    topbar_theme_button_width: int = 60
    topbar_user_width: int = 140
    landing_canvas_max_width: int = 1180
    landing_action_card_width: int = 236
    landing_hero_max_width: int = 690
    landing_logo_surface_size: int = 184
    landing_logo_size: int = 174
    landing_primary_button_height: int = 38
    # Operational Desktop additions (Phase 1). Additive only — legacy sizes untouched.
    panel_header_height: int = 24
    toolbar_strip_height: int = 28
    command_band_height: int = 36
    status_rail_height: int = 22
    row_height_dense: int = 20
    totals_dock_width: int = 200


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    typography: TypographyTokens = TypographyTokens()
    spacing: SpacingTokens = SpacingTokens()
    radius: RadiusTokens = RadiusTokens()
    sizes: SizeTokens = SizeTokens()


DEFAULT_TOKENS = ThemeTokens()
