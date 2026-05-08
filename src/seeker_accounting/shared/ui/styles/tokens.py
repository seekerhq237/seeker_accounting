from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TypographyTokens:
    family_primary: str = "Segoe UI"
    size_app_title: int = 20
    size_section_title: int = 14
    size_card_title: int = 13
    size_landing_wordmark: int = 50
    size_landing_tagline: int = 13
    size_body: int = 12
    size_small: int = 11
    size_dense: int = 11
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
    # Dialog / form layout (Payroll P1.S1) — semantic spacing for form primitives.
    dialog_padding: int = 20
    dialog_section_gap: int = 16
    dialog_field_gap: int = 8
    dialog_label_gap: int = 4
    dialog_footer_padding_v: int = 12
    dialog_footer_padding_h: int = 20
    issue_band_padding_v: int = 8
    issue_band_padding_h: int = 12
    issue_band_gap: int = 8
    inline_error_gap: int = 4


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
    topbar_height: int = 28
    topbar_control_height: int = 22
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
    # Ribbon (Sage-style single context-aware band, no tabs).
    # Phase 3: shell ribbon now renders via the shared adaptive CommandBar
    # (height 36 + 8 vertical margins). Was 64 in the legacy RibbonButton era.
    ribbon_height: int = 44
    ribbon_button_width: int = 60
    ribbon_button_icon_size: int = 26
    ribbon_divider_height: int = 40
    # Status chip (Phase 1)
    chip_height: int = 18
    chip_padding_h: int = 8
    chip_radius: int = 2
    chip_dot_size: int = 6
    # Adaptive command bar (Phase 1)
    command_bar_height: int = 36
    command_bar_button_height: int = 28
    command_bar_button_min_width: int = 64
    command_bar_button_padding_h: int = 10
    command_bar_icon_size: int = 16
    command_bar_overflow_width: int = 28
    command_bar_group_gap: int = 12
    command_bar_item_gap: int = 2
    # Enterprise data table (Phase 1)
    data_table_toolbar_height: int = 36
    data_table_header_height: int = 28
    data_table_row_height: int = 26
    data_table_row_height_dense: int = 22
    data_table_cell_padding_h: int = 10
    # Workflow stepper (Phase 2)
    workflow_stepper_height: int = 64
    workflow_stepper_dot_size: int = 22
    workflow_stepper_label_gap: int = 8
    workflow_stepper_step_min_width: int = 120
    workflow_stepper_connector_thickness: int = 2
    # Severity pill / inline-issue band (Payroll P1.S1)
    severity_pill_height: int = 18
    severity_pill_padding_h: int = 8
    severity_pill_radius: int = 4
    severity_pill_dot_size: int = 6
    issue_band_min_height: int = 32
    issue_band_radius: int = 4
    issue_band_accent_thickness: int = 3
    # KPI tile / workbench header (Payroll P1.S7)
    kpi_tile_min_width: int = 160
    kpi_tile_height: int = 72
    kpi_tile_radius: int = 4
    kpi_tile_padding_h: int = 14
    kpi_tile_padding_v: int = 10
    workbench_header_height: int = 52
    workbench_header_padding_h: int = 20
    # Side panel (Payroll P1.S3)
    side_panel_min_width: int = 320
    side_panel_max_width: int = 480
    # Dialog standard minimum sizes (P13.S1) — replace resize() literals
    dialog_min_w_small: int = 380
    dialog_min_h_small: int = 220
    dialog_min_w_medium: int = 480
    dialog_min_h_medium: int = 320
    dialog_min_w_large: int = 580
    dialog_min_h_large: int = 440
    dialog_min_w_xlarge: int = 760
    dialog_min_h_xlarge: int = 480
    dialog_min_w_document: int = 860
    dialog_min_h_document: int = 680
    # Minimum validation dialog
    dialog_min_w_validation: int = 560
    dialog_min_h_validation: int = 480
    # Form field standard widths (P13.S1)
    form_label_w: int = 160
    form_label_w_small: int = 120
    form_label_w_medium: int = 200
    form_combo_min_w: int = 260
    form_combo_large_min_w: int = 300
    form_textarea_h_small: int = 60
    form_textarea_h_medium: int = 80
    form_textarea_h_large: int = 96
    # Compact glyph column in checklists / status lists
    glyph_col_w: int = 18
    # Toolbar and filter widget widths (P13.S1)
    toolbar_filter_min_w: int = 220
    # Workbench pane minimum widths (P13.S1)
    workbench_pane_min_w: int = 360
    workbench_pane_min_w_wide: int = 420
    # Report tile height (P13.S1)
    report_tile_h: int = 64
    # Navigation pill minimum width (P13.S1)
    nav_pill_min_w: int = 140
    side_panel_padding: int = 16
    # Empty state (Payroll P1.S7)
    empty_state_max_width: int = 420
    empty_state_padding: int = 32
    empty_state_action_gap: int = 12


@dataclass(frozen=True, slots=True)
class SeverityTokens:
    """Severity ordering for inline-issue band, severity pills, and validation
    summaries. Values map 1:1 to ``severity_*`` palette colour groups.
    """
    # Ordered most-severe first; UI sorts/groups by this order.
    order: tuple[str, ...] = ("blocker", "error", "warning", "info", "notice")


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    typography: TypographyTokens = TypographyTokens()
    spacing: SpacingTokens = SpacingTokens()
    radius: RadiusTokens = RadiusTokens()
    sizes: SizeTokens = SizeTokens()
    severity: SeverityTokens = SeverityTokens()


DEFAULT_TOKENS = ThemeTokens()
