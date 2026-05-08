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
    # Semantic status chip families (Phase 1)
    status_success_bg: str
    status_success_fg: str
    status_success_border: str
    status_warning_bg: str
    status_warning_fg: str
    status_warning_border: str
    status_danger_bg: str
    status_danger_fg: str
    status_danger_border: str
    status_info_bg: str
    status_info_fg: str
    status_info_border: str
    status_neutral_bg: str
    status_neutral_fg: str
    status_neutral_border: str
    status_accent_bg: str
    status_accent_fg: str
    status_accent_border: str
    # Adaptive command bar surfaces (Phase 1)
    command_bar_surface: str
    command_bar_button_hover: str
    command_bar_button_pressed: str
    command_bar_separator: str
    # Enterprise data table surfaces (Phase 1)
    data_table_toolbar_surface: str
    data_table_header_bg: str
    data_table_header_fg: str
    data_table_grid_line: str
    data_table_row_alt: str
    data_table_row_selected: str
    data_table_row_selected_fg: str
    # Severity (Payroll P1.S1) — ordered: blocker > error > warning > info > notice.
    # Each row provides background, foreground, and an accent (for left-bar / dot).
    severity_blocker_bg: str
    severity_blocker_fg: str
    severity_blocker_accent: str
    severity_error_bg: str
    severity_error_fg: str
    severity_error_accent: str
    severity_warning_bg: str
    severity_warning_fg: str
    severity_warning_accent: str
    severity_info_bg: str
    severity_info_fg: str
    severity_info_accent: str
    severity_notice_bg: str
    severity_notice_fg: str
    severity_notice_accent: str


LIGHT_PALETTE = ThemePalette(
    name="light",
    # Operational Desktop: neutral gray base, restrained accent, flat framing.
    app_background="#EEF1F5",
    workspace_surface="#FFFFFF",
    secondary_surface="#F4F6FA",
    raised_surface="#FFFFFF",
    sidebar_surface="#E8ECF2",
    sidebar_hover="#DCE2EB",
    topbar_surface="#F4F6FA",
    border_default="#C6CEDA",
    border_strong="#AEB8C6",
    text_primary="#1A2230",
    text_secondary="#4E5866",
    text_muted="#7A8392",
    accent="#1F5BD8",
    accent_hover="#1A4EBA",
    accent_soft="#EEF3FE",
    accent_soft_strong="#D4E1FB",
    accent_text="#FFFFFF",
    success="#1E7A5A",
    warning="#9A6A17",
    danger="#B42E2E",
    info="#1F5BD8",
    input_surface="#FFFFFF",
    input_border="#C3CBD6",
    input_focus="#1F5BD8",
    table_header="#E8ECF2",
    table_hover="#F2F5F9",
    selected_fill="#D9E3F7",
    selected_text="#11223B",
    disabled_surface="#EAEDF2",
    disabled_text="#8A93A2",
    divider_subtle="#DDE3EA",
    # Semantic status chip families (Phase 1)
    status_success_bg="#E4F3EC",
    status_success_fg="#125C41",
    status_success_border="#A8D7C2",
    status_warning_bg="#F7EBD4",
    status_warning_fg="#704A0D",
    status_warning_border="#DFC178",
    status_danger_bg="#F8E2E2",
    status_danger_fg="#842020",
    status_danger_border="#E3A7A7",
    status_info_bg="#E7EEFC",
    status_info_fg="#1D45A5",
    status_info_border="#B7C9F3",
    status_neutral_bg="#EEF1F5",
    status_neutral_fg="#4E5866",
    status_neutral_border="#C6CEDA",
    status_accent_bg="#EEF3FE",
    status_accent_fg="#1F4FB8",
    status_accent_border="#BFD0F4",
    # Adaptive command bar surfaces (Phase 1)
    command_bar_surface="#F4F6FA",
    command_bar_button_hover="#E7ECF4",
    command_bar_button_pressed="#D8E0EA",
    command_bar_separator="#C6CEDA",
    # Enterprise data table surfaces (Phase 1)
    data_table_toolbar_surface="#F4F6FA",
    data_table_header_bg="#E6EBF2",
    data_table_header_fg="#2A3443",
    data_table_grid_line="#D6DDE7",
    data_table_row_alt="#F7F9FC",
    data_table_row_selected="#D9E3F7",
    data_table_row_selected_fg="#11223B",
    # Severity (Payroll P1.S1) — light theme
    severity_blocker_bg="#F0CBCB",
    severity_blocker_fg="#5F1515",
    severity_blocker_accent="#842020",
    severity_error_bg="#F8E2E2",
    severity_error_fg="#842020",
    severity_error_accent="#B42E2E",
    severity_warning_bg="#F7EBD4",
    severity_warning_fg="#704A0D",
    severity_warning_accent="#9A6A17",
    severity_info_bg="#E7EEFC",
    severity_info_fg="#1D45A5",
    severity_info_accent="#1F5BD8",
    severity_notice_bg="#EEF1F5",
    severity_notice_fg="#4E5866",
    severity_notice_accent="#7A8392",
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
    # Semantic status chip families (Phase 1)
    status_success_bg="#1B3328",
    status_success_fg="#6FD49C",
    status_success_border="#2A4F3B",
    status_warning_bg="#3A2A11",
    status_warning_fg="#E2B470",
    status_warning_border="#5A4220",
    status_danger_bg="#3A1F1B",
    status_danger_fg="#EC8A7E",
    status_danger_border="#5A2C26",
    status_info_bg="#1B2A45",
    status_info_fg="#8FB1F0",
    status_info_border="#2A4170",
    status_neutral_bg="#232A36",
    status_neutral_fg="#B3BAC4",
    status_neutral_border="#3A4352",
    status_accent_bg="#1E2B45",
    status_accent_fg="#9DB7EE",
    status_accent_border="#2E4577",
    # Adaptive command bar surfaces (Phase 1)
    command_bar_surface="#181D26",
    command_bar_button_hover="#232A36",
    command_bar_button_pressed="#2C3441",
    command_bar_separator="#2A313D",
    # Enterprise data table surfaces (Phase 1)
    data_table_toolbar_surface="#181D26",
    data_table_header_bg="#1E242F",
    data_table_header_fg="#C8CFD9",
    data_table_grid_line="#2A313D",
    data_table_row_alt="#1B2029",
    data_table_row_selected="#263A5A",
    data_table_row_selected_fg="#F0F3F7",
    # Severity (Payroll P1.S1) — dark theme
    severity_blocker_bg="#4A1612",
    severity_blocker_fg="#F4B5A9",
    severity_blocker_accent="#EC8A7E",
    severity_error_bg="#3A1F1B",
    severity_error_fg="#EC8A7E",
    severity_error_accent="#E7695A",
    severity_warning_bg="#3A2A11",
    severity_warning_fg="#E2B470",
    severity_warning_accent="#D9A54B",
    severity_info_bg="#1B2A45",
    severity_info_fg="#8FB1F0",
    severity_info_accent="#6A9BF3",
    severity_notice_bg="#232A36",
    severity_notice_fg="#B3BAC4",
    severity_notice_accent="#7F8895",
)


def get_palette(theme_name: str) -> ThemePalette:
    return DARK_PALETTE if theme_name.lower() == "dark" else LIGHT_PALETTE
