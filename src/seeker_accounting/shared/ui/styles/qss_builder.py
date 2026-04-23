from __future__ import annotations

from seeker_accounting.shared.ui.styles.palette import ThemePalette
from seeker_accounting.shared.ui.styles.tokens import ThemeTokens


def build_stylesheet(palette: ThemePalette, tokens: ThemeTokens) -> str:
    typography = tokens.typography
    radius = tokens.radius
    sizes = tokens.sizes

    return f"""
QWidget {{
    background: {palette.app_background};
    color: {palette.text_primary};
    font-family: {typography.family_primary};
    font-size: {typography.size_body}px;
}}

QMainWindow {{
    background: {palette.app_background};
}}

QDialog {{
    background: {palette.secondary_surface};
}}

QFrame#ShellRoot {{
    background: {palette.app_background};
}}

QFrame#LandingRoot {{
    background: {palette.app_background};
}}

QWidget#LandingHeroZone,
QWidget#LandingActionZone {{
    background: transparent;
}}

QLabel#LandingWordmarkStrong {{
    color: {palette.text_primary};
    font-size: {typography.size_landing_wordmark}px;
    font-weight: 700;
}}

QLabel#LandingWordmarkSoft {{
    color: {palette.text_primary};
    font-size: {typography.size_landing_wordmark}px;
    font-weight: {typography.weight_regular};
}}

QLabel#LandingTagline {{
    color: {palette.text_secondary};
    font-size: {typography.size_landing_tagline}px;
    font-weight: {typography.weight_medium};
}}

QLabel#LandingVersionLabel {{
    color: {palette.text_muted};
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_medium};
}}

QPushButton#LandingAdminTrigger {{
    background: transparent;
    border: none;
    color: rgba(255, 255, 255, 0.12);
    padding: 0;
    font-size: 15px;
}}

QPushButton#LandingAdminTrigger:hover {{
    color: rgba(255, 255, 255, 0.38);
    background: transparent;
    border: none;
}}

QPushButton#LandingLoginButton {{
    min-height: {sizes.landing_primary_button_height}px;
    font-weight: {typography.weight_semibold};
    font-size: {typography.size_body}px;
}}

QPushButton#LandingSecondaryAction {{
    min-height: 24px;
    background: transparent;
    border: none;
    color: {palette.text_muted};
    padding: 0;
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_medium};
    text-align: right;
}}

QPushButton#LandingSecondaryAction:hover {{
    color: {palette.accent};
    background: transparent;
    border: none;
}}

QPushButton#LandingSecondaryAction:focus {{
    color: {palette.accent_hover};
    background: transparent;
    border: none;
    padding: 0;
}}

QFrame#Sidebar {{
    background: {palette.sidebar_surface};
    border-right: 1px solid {palette.border_default};
}}

QFrame#SidebarHeader {{
    background: transparent;
    border-bottom: 1px solid {palette.divider_subtle};
}}

QFrame#SidebarContextPanel {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0;
}}

QScrollArea#SidebarScroll {{
    background: transparent;
    border: none;
}}

QWidget#SidebarScrollContent {{
    background: transparent;
}}

QLabel#SidebarCompanyLogo {{
    background: {palette.accent_soft};
    border: 1px solid {palette.accent_soft_strong};
    border-radius: {radius.small}px;
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_medium};
}}

QLabel#UserAvatarPreview {{
    border-radius: 36px;
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_semibold};
    padding: 0;
}}

QLabel#UserAvatarPreview[avatarMode="fallback"] {{
    background: {palette.accent_soft};
    border: 2px solid {palette.accent_soft_strong};
    color: {palette.accent};
}}

QLabel#UserAvatarPreview[avatarMode="image"] {{
    background: {palette.workspace_surface};
    border: 2px solid {palette.border_default};
    color: transparent;
}}

QLabel#SectionLabel,
QLabel[role="caption"],
QLabel#PageEyebrow {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_medium};
    text-transform: uppercase;
}}

QLabel#SidebarCompanyName,
QLabel#PageTitle,
QLabel#TopBarValue,
QLabel#CurrentPageLabel,
QLabel#TopBarChipValue,
QLabel#TopBarCompanyName,
QLabel#TopBarProfileName {{
    color: {palette.text_primary};
    font-weight: {typography.weight_semibold};
}}

QLabel#SidebarCompanyName,
QLabel#CurrentPageLabel {{
    font-size: {typography.size_card_title}px;
}}

QLabel#SidebarCompanyName {{
    font-size: 14px;
}}

QLabel#TopBarValue {{
    font-size: {typography.size_dense}px;
}}

QLabel#TopBarChipValue,
QLabel#TopBarCompanyName,
QLabel#TopBarProfileName {{
    font-size: {typography.size_body}px;
}}

QLabel#PageTitle {{
    font-size: {typography.size_section_title}px;
}}

QLabel#PageSummary,
QLabel#TopBarMeta,
QLabel#CurrentPageSummary,
QLabel#CardBodyLabel,
QLabel#ValueLabel,
QLabel#TopBarChipLabel,
QLabel#TopBarProfileRole,
QLabel#TopBarSearchPlaceholder {{
    color: {palette.text_secondary};
}}

QLabel#TopBarMeta,
QLabel#CurrentPageSummary,
QLabel#InfoCardLine,
QLabel#PageSummary,
QLabel#TopBarChipLabel,
QLabel#TopBarProfileRole,
QLabel#TopBarSearchPlaceholder,
QLabel#TopBarProfileChevron {{
    font-size: {typography.size_dense}px;
}}

QLabel#TopBarCompanyName[companyState="empty"] {{
    color: {palette.text_muted};
    font-weight: {typography.weight_medium};
}}

QLabel#TopBarCompanyName,
QLabel#TopBarChipValue,
QLabel#TopBarProfileName,
QLabel#TopBarSearchPlaceholder,
QLabel#TopBarProfileChevron {{
    background: transparent;
}}

QLabel#CompanyLogoPreview {{
    background: {palette.secondary_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.small}px;
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_medium};
}}

QLabel#CompanyLogoFileName {{
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
}}

QFrame#TopBar,
QFrame#CommandBand {{
    background: {palette.topbar_surface};
    border: none;
    border-bottom: 1px solid {palette.border_strong};
    border-radius: 0;
    min-height: {sizes.topbar_height}px;
    max-height: {sizes.topbar_height}px;
}}

QFrame#TopBar > QWidget,
QFrame#CommandBand > QWidget {{
    background: transparent;
}}

/* Menu-bar corner cluster: no frame, no forced height. */
QFrame#ShellMenuCorner {{
    background: transparent;
    border: none;
}}

QFrame#ShellMenuCorner > QWidget {{
    background: transparent;
}}

/* ── Operational Desktop — Menu Bar band ─────────────── */

QMenuBar#ShellMenuBar {{
    background: {palette.secondary_surface};
    color: {palette.text_primary};
    border: none;
    border-bottom: 1px solid {palette.border_default};
    padding: 1px 4px;
    font-size: {typography.size_small}px;
}}

QMenuBar#ShellMenuBar::item {{
    background: transparent;
    color: {palette.text_primary};
    padding: 2px 8px;
    margin: 0 1px;
    border-radius: {radius.small}px;
}}

QMenuBar#ShellMenuBar::item:selected {{
    background: {palette.sidebar_hover};
    color: {palette.text_primary};
}}

QMenuBar#ShellMenuBar::item:pressed {{
    background: {palette.selected_fill};
}}

QFrame#TopBarDivider {{
    background: {palette.border_default};
}}

QPushButton#TopBarSidebarToggle {{
    min-width: {sizes.topbar_control_height}px;
    max-width: {sizes.topbar_control_height}px;
    min-height: {sizes.topbar_control_height}px;
    max-height: {sizes.topbar_control_height}px;
    border-radius: {radius.medium}px;
    padding: 0;
    background: transparent;
    border: 1px solid transparent;
    color: {palette.text_secondary};
    font-size: 18px;
    font-weight: {typography.weight_semibold};
}}

QPushButton#TopBarSidebarToggle:hover {{
    background: {palette.secondary_surface};
    border-color: {palette.border_default};
    color: {palette.text_primary};
}}

QPushButton#TopBarSidebarToggle:focus {{
    padding: 0;
}}

QPushButton#TopBarSidebarToggle[sidebarCollapsed="true"] {{
    background: {palette.accent_soft};
    border-color: {palette.accent_soft_strong};
    color: {palette.accent};
}}

QFrame#TopBarSearchTrigger,
QFrame#TopBarChip,
QFrame#TopBarProfileChip {{
    background: {palette.secondary_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.medium}px;
}}

QFrame#TopBarProfileChip {{
    min-height: 20px;
}}

QFrame#TopBarSearchTrigger {{
    border-color: {palette.border_strong};
}}

QFrame#TopBarChip {{
    min-height: 20px;
}}

QFrame#TopBarChip[chipKind="fiscal"][fiscalTone="success"] {{
    background: rgba(19, 121, 91, 0.08);
    border-color: rgba(19, 121, 91, 0.20);
}}

QFrame#TopBarChip[chipKind="fiscal"][fiscalTone="warning"] {{
    background: rgba(183, 121, 31, 0.08);
    border-color: rgba(183, 121, 31, 0.20);
}}

QFrame#TopBarChip[chipKind="fiscal"][fiscalTone="danger"] {{
    background: rgba(197, 48, 48, 0.08);
    border-color: rgba(197, 48, 48, 0.18);
}}

QFrame#TopBarChip[chipKind="fiscal"][fiscalTone="info"] {{
    background: {palette.accent_soft};
    border-color: {palette.accent_soft_strong};
}}

QFrame#TopBarSearchTrigger:hover,
QFrame#TopBarProfileChip:hover {{
    background: {palette.raised_surface};
    border-color: {palette.border_strong};
}}

QFrame#TopBarSearchTrigger:focus,
QFrame#TopBarProfileChip:focus {{
    border: 2px solid {palette.input_focus};
}}

QLabel#TopBarSearchPlaceholder {{
    color: {palette.text_muted};
    font-size: {typography.size_body}px;
}}

QLabel#TopBarShortcutHint {{
    color: {palette.text_secondary};
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.small}px;
    padding: 1px 4px;
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_medium};
}}

QLabel#TopBarChipLabel {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
}}

QLabel#TopBarStatusDot {{
    min-width: 6px;
    max-width: 6px;
    min-height: 6px;
    max-height: 6px;
    border-radius: 3px;
    background: {palette.text_muted};
}}

QLabel#TopBarStatusDot[statusTone="success"] {{
    background: {palette.success};
}}

QLabel#TopBarStatusDot[statusTone="warning"] {{
    background: {palette.warning};
}}

QLabel#TopBarStatusDot[statusTone="danger"] {{
    background: {palette.danger};
}}

QLabel#TopBarStatusDot[statusTone="info"] {{
    background: {palette.info};
}}

QLabel#TopBarStatusDot[statusTone="neutral"] {{
    background: {palette.text_muted};
}}

QLabel#TopBarAvatar {{
    border-radius: 8px;
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_semibold};
    padding: 0;
}}

QLabel#TopBarAvatar[avatarMode="fallback"] {{
    background: {palette.accent_soft};
    border: 1px solid {palette.accent_soft_strong};
    color: {palette.accent};
}}

QLabel#TopBarAvatar[avatarMode="image"] {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    color: transparent;
}}

QLabel#TopBarProfileChevron {{
    color: {palette.text_muted};
}}

/* ── Phase 2 — Company Switcher ───────────────────────────── */

QFrame#TopBarCompanySwitcher {{
    background: {palette.secondary_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.medium}px;
    min-height: {sizes.topbar_control_height}px;
}}

QFrame#TopBarCompanySwitcher:hover {{
    background: {palette.raised_surface};
    border-color: {palette.border_strong};
}}

/* ── Phase 2 — Theme Toggle + Bell ───────────────────────── */

QPushButton#TopBarThemeToggle,
QPushButton#TopBarBellButton {{
    background: transparent;
    border: none;
    border-radius: {radius.small}px;
    padding: 0;
}}

QPushButton#TopBarThemeToggle:hover,
QPushButton#TopBarBellButton:hover {{
    background: {palette.raised_surface};
}}

QPushButton#TopBarThemeToggle:focus,
QPushButton#TopBarBellButton:focus {{
    border: 2px solid {palette.input_focus};
}}

/* ── Phase 2 — New Button ────────────────────────────────── */

QToolButton#TopBarNewButton {{
    background: {palette.accent};
    color: {palette.accent_text};
    border: none;
    border-radius: {radius.medium}px;
    padding: 0 12px;
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_medium};
    min-height: {sizes.topbar_control_height}px;
}}

QToolButton#TopBarNewButton:hover {{
    background: {palette.accent_hover};
}}

QToolButton#TopBarNewButton:pressed {{
    background: {palette.accent_hover};
}}

QToolButton#TopBarNewButton::menu-indicator {{
    image: none;
    width: 0;
}}

QMenu#TopBarNewMenu {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.medium}px;
    padding: 4px 0;
    font-size: {typography.size_body}px;
}}

QMenu#TopBarNewMenu::item {{
    padding: 6px 16px;
    color: {palette.text_primary};
    background: transparent;
}}

QMenu#TopBarNewMenu::item:selected {{
    background: {palette.accent_soft};
    color: {palette.accent};
    border-radius: {radius.small}px;
}}

QMenu#TopBarNewMenu::item:disabled {{
    color: {palette.text_muted};
}}

QMenu#TopBarNewMenu::separator {{
    height: 1px;
    background: {palette.border_default};
    margin: 4px 0;
}}

/* ── Phase 2 — Search Input ──────────────────────────────── */

QLineEdit#TopBarSearchInput {{
    background: transparent;
    border: none;
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
    padding: 0;
    selection-background-color: {palette.accent_soft};
    selection-color: {palette.accent};
}}

QLineEdit#TopBarSearchInput::placeholder {{
    color: {palette.text_muted};
}}

/* ── Phase 2 — Notification Panel ───────────────────────── */

QFrame#NotificationPanel {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.large}px;
}}

QWidget#NotificationPanelHeader {{
    background: transparent;
}}

QLabel#NotificationPanelTitle {{
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_semibold};
}}

QFrame#NotificationPanelSeparator {{
    background: {palette.border_default};
    border: none;
}}

QFrame#NotificationRow {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {palette.border_default};
}}

QFrame#NotificationRow:hover {{
    background: {palette.secondary_surface};
}}

QLabel#NotificationDot {{
    border-radius: 4px;
    background: {palette.text_muted};
}}

QLabel#NotificationDot[notifTone="warning"] {{
    background: {palette.warning};
}}

QLabel#NotificationDot[notifTone="danger"] {{
    background: {palette.danger};
}}

QLabel#NotificationDot[notifTone="info"] {{
    background: {palette.info};
}}

QLabel#NotificationTitle {{
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_medium};
}}

QLabel#NotificationBody {{
    color: {palette.text_secondary};
    font-size: {typography.size_caption}px;
}}

QLabel#NotificationEmptyLabel {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
    padding: 16px;
}}

/* ── Operational Desktop — Status Rail ─────────────────── */

QFrame#StatusBar {{
    background: {palette.secondary_surface};
    border: none;
    border-top: 1px solid {palette.border_default};
    border-radius: 0;
    min-height: {sizes.status_rail_height}px;
    max-height: {sizes.status_rail_height}px;
}}

QLabel#StatusBarContext {{
    color: {palette.text_secondary};
    font-size: {typography.size_caption}px;
}}

QLabel#StatusBarMeta {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
}}

/* ── Phase 2 — Sidebar Search ────────────────────────────── */

QWidget#SidebarSearchBar {{
    background: transparent;
}}

QLineEdit#SidebarSearchInput {{
    background: {palette.secondary_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.small}px;
    color: {palette.text_secondary};
    font-size: {typography.size_caption}px;
    padding: 4px 8px;
    selection-background-color: {palette.accent_soft};
    selection-color: {palette.accent};
}}

QLineEdit#SidebarSearchInput:focus {{
    border-color: {palette.input_focus};
    background: {palette.raised_surface};
}}

QLineEdit#SidebarSearchInput::placeholder {{
    color: {palette.text_muted};
}}

/* ── Phase 2 — Sidebar Sections (Favorites / Recents) ─────── */

QWidget#SidebarSection {{
    background: transparent;
}}

QLabel#SidebarSectionLabel {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_medium};
    padding: 4px 4px 2px 4px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}

QFrame#SidebarSectionSeparator {{
    background: {palette.border_default};
    border: none;
    min-height: 1px;
    max-height: 1px;
    margin: 4px 0;
}}

QPushButton#SidebarFavoriteButton,
QPushButton#SidebarRecentButton {{
    background: transparent;
    border: none;
    border-radius: {radius.small}px;
    color: {palette.text_secondary};
    font-size: {typography.size_body}px;
    padding: 5px 8px;
    text-align: left;
}}

QPushButton#SidebarFavoriteButton:hover,
QPushButton#SidebarRecentButton:hover {{
    background: {palette.secondary_surface};
    color: {palette.text_primary};
}}

QPushButton#SidebarFavoriteButton:checked,
QPushButton#SidebarRecentButton:checked {{
    background: {palette.accent_soft};
    color: {palette.accent};
}}

/* ── Phase 2 — Sidebar Nav Badge ─────────────────────────── */

QLabel#SidebarNavBadge {{
    background: {palette.accent_soft};
    color: {palette.accent};
    border-radius: 8px;
    padding: 1px 5px;
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_medium};
    min-width: 16px;
}}

QFrame#WorkspaceFrame {{
    background: {palette.secondary_surface};
}}

QFrame#PageCard {{
    background: transparent;
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

QFrame#PageToolbar,
QFrame#DialogSectionCard,
QFrame#GuidedResolutionHeaderCard,
QFrame[card="true"] {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

QFrame#GuidedResolutionHeaderCard {{
    background: {palette.raised_surface};
}}

QFrame#InfoCard {{
    background: {palette.raised_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

/* ---------- Operational Desktop primitives ---------- */

QFrame#Panel {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0;
}}

QFrame#PanelHeader {{
    background: {palette.secondary_surface};
    border: none;
    border-bottom: 1px solid {palette.border_default};
    border-radius: 0;
    min-height: {sizes.panel_header_height}px;
    max-height: {sizes.panel_header_height}px;
}}

QLabel#PanelHeaderTitle {{
    color: {palette.text_primary};
    font-size: {typography.size_small}px;
    font-weight: {typography.weight_semibold};
    padding: 0 10px;
    letter-spacing: 0.2px;
}}

QLabel#PanelHeaderCaption {{
    color: {palette.text_secondary};
    font-size: {typography.size_caption}px;
    padding: 0 10px;
}}

QFrame#ToolbarStrip {{
    background: {palette.secondary_surface};
    border: none;
    border-bottom: 1px solid {palette.border_default};
    border-radius: 0;
    min-height: {sizes.toolbar_strip_height}px;
    max-height: {sizes.toolbar_strip_height}px;
}}

QFrame#ActionBand {{
    background: {palette.workspace_surface};
    border: none;
    border-top: 1px solid {palette.divider_subtle};
    border-bottom: 1px solid {palette.border_default};
    border-radius: 0;
    min-height: 22px;
    max-height: 22px;
}}

QFrame#ActionBand QPushButton,
QFrame#ActionBand QToolButton {{
    min-height: 16px;
    max-height: 16px;
    padding: 1px 8px;
}}

QFrame#CommandBand {{
    background: {palette.topbar_surface};
    border: none;
    border-bottom: 1px solid {palette.border_strong};
    border-radius: 0;
    min-height: {sizes.command_band_height}px;
    max-height: {sizes.command_band_height}px;
}}

QFrame#CommandBandGroup {{
    background: transparent;
    border: none;
    border-right: 1px solid {palette.divider_subtle};
    border-radius: 0;
}}

QFrame#CommandBandGroup[groupEdge="end"] {{
    border-right: none;
}}

QFrame#StatusRail {{
    background: {palette.secondary_surface};
    border: none;
    border-top: 1px solid {palette.border_default};
    border-radius: 0;
    min-height: {sizes.status_rail_height}px;
    max-height: {sizes.status_rail_height}px;
}}

QLabel#StatusRailText {{
    color: {palette.text_secondary};
    font-size: {typography.size_caption}px;
    padding: 0 10px;
}}

QFrame#DocumentWorkspace {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0;
}}

QFrame#DocumentCommandRow {{
    background: {palette.secondary_surface};
    border: none;
    border-bottom: 1px solid {palette.border_default};
    border-radius: 0;
    min-height: {sizes.toolbar_strip_height}px;
    max-height: {sizes.toolbar_strip_height}px;
}}

QFrame#DocumentBody {{
    background: {palette.workspace_surface};
    border: none;
}}

QFrame#DocumentLinesHost {{
    background: {palette.workspace_surface};
    border: none;
}}

QFrame#DocumentLinesGrid {{
    background: {palette.workspace_surface};
    border: none;
    border-radius: 0;
}}

QFrame#DocumentIdentityStrip {{
    background: {palette.secondary_surface};
    border: none;
    border-bottom: 1px solid {palette.border_default};
    border-radius: 0;
}}

/* ── Sage-style context-aware ribbon ───────────────────────────────── */

QFrame#RibbonBar {{
    background: {palette.secondary_surface};
    border: none;
    border-bottom: 1px solid {palette.border_default};
    border-radius: 0;
    min-height: {sizes.ribbon_height}px;
    max-height: {sizes.ribbon_height}px;
}}

QStackedWidget#RibbonStack {{
    background: transparent;
    border: none;
}}

QWidget#RibbonSurface {{
    background: transparent;
    border: none;
}}

QWidget#RibbonPlaceholder {{
    background: transparent;
    border: none;
}}

QFrame#RibbonDivider {{
    color: {palette.divider_subtle};
    background: {palette.divider_subtle};
    border: none;
    margin: 0 6px;
}}

QToolButton#RibbonButton {{
    background: transparent;
    color: {palette.text_primary};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 2px 2px 2px;
    margin: 2px 1px;
    font-size: {typography.size_caption}px;
}}

QToolButton#RibbonButton:hover {{
    background: {palette.sidebar_hover};
    border: 1px solid {palette.border_default};
}}

QToolButton#RibbonButton:pressed {{
    background: {palette.accent_soft_strong};
    border: 1px solid {palette.border_strong};
}}

QToolButton#RibbonButton:focus {{
    border: 1px solid {palette.accent};
}}

QToolButton#RibbonButton:disabled {{
    color: {palette.disabled_text};
    background: transparent;
    border: 1px solid transparent;
}}

QToolButton#RibbonButton[ribbonVariant="primary"] {{
    color: {palette.accent};
}}

QToolButton#RibbonButton[ribbonVariant="danger"] {{
    color: {palette.danger};
}}

/* ── Top-level child document windows ──────────────────────────────── */

QWidget#ChildWindowRoot {{
    background: {palette.workspace_surface};
}}

QFrame#ChildWindowRibbonHost {{
    background: {palette.secondary_surface};
    border: none;
    border-bottom: 1px solid {palette.border_default};
}}

QFrame#ChildWindowBody {{
    background: {palette.workspace_surface};
    border: none;
}}

QFrame#MetaStrip {{
    background: {palette.workspace_surface};
    border: none;
    border-bottom: 1px solid {palette.divider_subtle};
    border-radius: 0;
}}

QLabel#MetaLabel {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
}}

QLabel#MetaValue {{
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_medium};
}}

QFrame#TotalsDock {{
    background: {palette.secondary_surface};
    border: none;
    border-left: 1px solid {palette.border_default};
    border-radius: 0;
    min-width: {sizes.totals_dock_width}px;
    max-width: {sizes.totals_dock_width}px;
}}

QFrame#ActionRail {{
    background: {palette.secondary_surface};
    border: none;
    border-top: 1px solid {palette.border_strong};
    border-radius: 0;
}}

QPushButton[role="primary"] {{
    background: {palette.accent};
    color: {palette.accent_text};
    border: 1px solid {palette.accent};
}}

QPushButton[role="primary"]:hover {{
    background: {palette.accent_hover};
    border-color: {palette.accent_hover};
}}

QPushButton[role="primary"]:pressed {{
    background: {palette.accent_hover};
    border-color: {palette.accent_hover};
}}

QToolButton#GuidedResolutionDetailsToggle {{
    border: none;
    background: transparent;
    color: {palette.text_secondary};
    padding: 0;
    min-height: 22px;
}}

QTextEdit#GuidedResolutionDetailsText {{
    background: {palette.secondary_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.small}px;
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
}}

QLabel#InfoCardTitle,
QLabel#CardTitle,
QLabel#EmptyStateTitle,
QLabel#DialogSectionTitle {{
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_primary};
}}

QLabel#ToolbarTitle {{
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_primary};
    padding: 0 4px 0 2px;
}}

QLabel#DialogSectionSummary,
QLabel#ToolbarMeta {{
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
}}

QLabel#ToolbarValue {{
    color: {palette.text_primary};
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_semibold};
}}

QLabel#ToolbarValue[imbalanceState="balanced"] {{
    color: {palette.success};
}}

QLabel#ToolbarValue[imbalanceState="imbalanced"] {{
    color: {palette.danger};
}}

QLabel#InfoCardLine {{
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
}}

QLabel#LinesEmptyState {{
    color: {palette.text_muted};
    font-size: {typography.size_body}px;
    padding: 32px;
}}

QLabel#TotalsValue {{
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_semibold};
    min-width: 100px;
}}

QLabel#TotalsGrandTotal {{
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_semibold};
    min-width: 100px;
}}

QFrame#TotalsSeparator {{
    color: {palette.border_default};
    max-height: 1px;
}}

QLabel#DialogErrorLabel {{
    background: rgba(183, 121, 31, 0.14);
    color: {palette.warning};
    border: 1px solid rgba(183, 121, 31, 0.24);
    border-radius: {radius.small}px;
    padding: 8px 10px;
}}

QLabel#WizardStepPill {{
    background: {palette.secondary_surface};
    color: {palette.text_secondary};
    border: 1px solid {palette.border_default};
    border-radius: 0;
    min-width: 112px;
    padding: 6px 10px;
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_semibold};
}}

QLabel#WizardStepPill[current="true"] {{
    background: {palette.accent_soft};
    color: {palette.accent};
    border-color: {palette.accent_soft_strong};
}}

QLabel#WizardStepPill[completed="true"] {{
    background: {palette.workspace_surface};
    color: {palette.text_primary};
}}

QLabel[chipTone="info"],
QLabel[chipTone="success"],
QLabel[chipTone="warning"],
QLabel[chipTone="danger"],
QLabel[chipTone="neutral"] {{
    border-radius: {radius.small}px;
    padding: 4px 8px;
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_semibold};
}}

QLabel[chipTone="info"] {{
    background: {palette.accent_soft};
    color: {palette.accent};
    border: 1px solid {palette.accent_soft_strong};
}}

QLabel[chipTone="success"] {{
    background: rgba(19, 121, 91, 0.12);
    color: {palette.success};
    border: 1px solid rgba(19, 121, 91, 0.22);
}}

QLabel[chipTone="warning"] {{
    background: rgba(183, 121, 31, 0.14);
    color: {palette.warning};
    border: 1px solid rgba(183, 121, 31, 0.24);
}}

QLabel[chipTone="danger"] {{
    background: rgba(197, 48, 48, 0.12);
    color: {palette.danger};
    border: 1px solid rgba(197, 48, 48, 0.22);
}}

QLabel[chipTone="neutral"] {{
    background: {palette.secondary_surface};
    color: {palette.text_secondary};
    border: 1px solid {palette.border_default};
}}

/* ── Dashboard ────────────────────────────────────────────────── */

QWidget#DashboardPage,
QWidget#DashboardContainer {{
    background: {palette.app_background};
}}

QWidget#DashboardContextRow {{
    background: transparent;
}}

/* Context row */
QLabel#DashboardContextLabel {{
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
    font-weight: {typography.weight_medium};
}}

QPushButton#DashboardRefreshButton {{
    background: transparent;
    border: 1px solid {palette.border_default};
    border-radius: 0;
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
    padding: 4px 10px;
    min-height: 26px;
}}

QPushButton#DashboardRefreshButton:hover {{
    background: {palette.accent_soft};
    border-color: {palette.accent};
    color: {palette.accent};
}}

/* Tab bar */
QTabBar#DashboardTabBar {{
    background: transparent;
    border: none;
}}

QTabBar#DashboardTabBar::tab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: {palette.text_secondary};
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_regular};
    padding: 8px 16px;
    margin-right: 2px;
}}

QTabBar#DashboardTabBar::tab:selected {{
    color: {palette.accent};
    border-bottom: 2px solid {palette.accent};
    font-weight: {typography.weight_semibold};
}}

QTabBar#DashboardTabBar::tab:hover:!selected {{
    color: {palette.text_primary};
    border-bottom: 2px solid {palette.border_strong};
}}

/* Content panels */
QFrame#DashboardPanel {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

QLabel#DashboardSectionTitle {{
    font-size: {typography.size_dense}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_primary};
    letter-spacing: 0.4px;
    text-transform: uppercase;
}}

QLabel#DashboardEmptyLabel {{
    color: {palette.text_muted};
    font-size: {typography.size_body}px;
}}

/* Aging buckets */
QLabel#DashboardAgingBucketLabel {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
}}

QLabel#DashboardAgingBucketValue {{
    color: {palette.text_primary};
    font-size: {typography.size_dense}px;
    font-weight: {typography.weight_medium};
}}

QLabel#DashboardAgingTotal {{
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_semibold};
}}

/* Quick actions */
QPushButton#DashboardQuickAction {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0;
    color: {palette.text_primary};
    font-size: {typography.size_dense}px;
    font-weight: {typography.weight_medium};
    padding: 10px 6px;
    min-height: 36px;
}}

QPushButton#DashboardQuickAction:hover {{
    background: {palette.accent_soft};
    border-color: {palette.accent};
    color: {palette.accent};
}}

QPushButton#DashboardQuickAction:pressed {{
    background: {palette.accent};
    color: {palette.accent_text};
}}

/* Attention rows */
QFrame#DashboardAttentionRow {{
    border: none;
    background: transparent;
}}

QFrame#DashboardAttentionRow:hover {{
    background: {palette.table_hover};
    border-radius: {radius.small}px;
}}

QLabel#DashboardAttentionDot {{
    border-radius: 4px;
}}

QLabel#DashboardAttentionDot[severity="danger"]  {{ background: {palette.danger}; }}
QLabel#DashboardAttentionDot[severity="warning"] {{ background: {palette.warning}; }}
QLabel#DashboardAttentionDot[severity="info"]    {{ background: {palette.accent}; }}

QLabel#DashboardAttentionLabel {{
    color: {palette.text_primary};
    font-size: {typography.size_dense}px;
}}

QLabel#DashboardAttentionCount {{
    color: {palette.text_secondary};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_semibold};
}}

QLabel#DashboardAttentionCount[severity="danger"]  {{ color: {palette.danger}; }}
QLabel#DashboardAttentionCount[severity="warning"] {{ color: {palette.warning}; }}

/* Cash & Liquidity tab balance cards */
QFrame#DashboardBalanceCardBlue,
QFrame#DashboardBalanceCardGreen,
QFrame#DashboardBalanceCardAmber {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
    min-height: 70px;
}}

QFrame#DashboardBalanceCardBlue  {{ border-top: 3px solid {palette.accent}; }}
QFrame#DashboardBalanceCardGreen {{ border-top: 3px solid {palette.success}; }}
QFrame#DashboardBalanceCardAmber {{ border-top: 3px solid {palette.warning}; }}

QLabel#DashboardBalanceCardTitle {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_medium};
}}

QLabel#DashboardBalanceCardValue {{
    color: {palette.text_primary};
    font-size: {typography.size_section_title}px;
    font-weight: {typography.weight_semibold};
}}

/* Cash trend chart legend */
QLabel#DashboardTrendLegendInflow {{
    background: {palette.success};
    border-radius: 2px;
}}
QLabel#DashboardTrendLegendOutflow {{
    background: {palette.warning};
    border-radius: 2px;
}}
QLabel#DashboardTrendLegendLabel {{
    color: {palette.text_muted};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_medium};
    margin-right: 8px;
}}

/* No-company state */
QFrame#DashboardNoCompanyCard {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

QLabel#DashboardNoCompanyTitle {{
    color: {palette.text_primary};
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_semibold};
}}

QLabel#DashboardNoCompanyBody {{
    color: {palette.text_secondary};
    font-size: {typography.size_body}px;
}}

/* ── End Dashboard ────────────────────────────────────────────── */

QPushButton,
QToolButton,
QComboBox,
QLineEdit,
QDateEdit,
QSpinBox,
QDoubleSpinBox,
QPlainTextEdit,
QTextEdit {{
    min-height: {sizes.control_height}px;
    border-radius: {radius.small}px;
}}

QPushButton,
QToolButton {{
    border: 1px solid {palette.border_default};
    background: {palette.workspace_surface};
    color: {palette.text_primary};
    padding: 2px 8px;
    min-height: 22px;
    font-weight: {typography.weight_medium};
}}

QPushButton:hover,
QToolButton:hover {{
    background: {palette.secondary_surface};
    border-color: {palette.border_strong};
}}

QPushButton:pressed,
QToolButton:pressed {{
    background: {palette.accent_soft};
}}

QPushButton:disabled,
QToolButton:disabled {{
    background: {palette.disabled_surface};
    color: {palette.disabled_text};
    border-color: {palette.border_default};
}}

QPushButton:focus,
QToolButton:focus {{
    border: 1px solid {palette.input_focus};
    padding: 2px 8px;
}}

QPushButton[variant="primary"] {{
    background: {palette.accent};
    color: {palette.accent_text};
    border-color: {palette.accent};
}}

QPushButton[variant="primary"]:hover {{
    background: {palette.accent_hover};
    border-color: {palette.accent_hover};
}}

QPushButton[variant="secondary"] {{
    background: {palette.workspace_surface};
    color: {palette.text_primary};
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    border-color: transparent;
    color: {palette.text_secondary};
}}

QPushButton[variant="ghost"]:hover {{
    background: {palette.secondary_surface};
    border-color: {palette.border_default};
    color: {palette.text_primary};
}}

QPushButton[moduleParent="true"] {{
    min-height: {sizes.sidebar_parent_height}px;
    text-align: left;
    padding: 0 10px;
    border: none;
    border-radius: {radius.small}px;
    background: transparent;
    color: {palette.text_secondary};
    font-weight: {typography.weight_medium};
    font-size: {typography.size_dense}px;
}}

QPushButton[moduleParent="true"]:hover {{
    background: {palette.sidebar_hover};
    color: {palette.text_primary};
}}

QPushButton[moduleParent="true"][moduleOpen="true"] {{
    background: {palette.sidebar_hover};
    color: {palette.text_primary};
    font-weight: {typography.weight_semibold};
}}

QPushButton[moduleParent="true"][moduleActive="true"] {{
    color: {palette.accent};
    background: {palette.accent_soft};
    font-weight: {typography.weight_semibold};
}}

QPushButton[moduleParent="true"]:focus {{
    border: 1px solid {palette.input_focus};
}}

QFrame#Sidebar[sidebarCollapsed="true"] QPushButton[moduleParent="true"] {{
    padding: 0;
    text-align: center;
}}

QPushButton[childNav="true"] {{
    min-height: {sizes.sidebar_child_height}px;
    text-align: left;
    padding: 0 10px 0 34px;
    border: none;
    border-radius: {radius.small}px;
    background: transparent;
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
    font-weight: {typography.weight_regular};
}}

QPushButton[childNav="true"]:hover {{
    background: {palette.sidebar_hover};
    color: {palette.text_primary};
}}

QPushButton[childNav="true"]:checked {{
    color: {palette.accent};
    background: {palette.accent_soft};
    font-weight: {typography.weight_semibold};
}}

QPushButton[childNav="true"]:focus {{
    border: 1px solid {palette.input_focus};
}}

QWidget[childContainer="true"] {{
    background: transparent;
}}

QWidget#RegisterTableHost {{
    background: {palette.workspace_surface};
}}

QLineEdit,
QComboBox,
QDateEdit,
QSpinBox,
QDoubleSpinBox,
QPlainTextEdit,
QTextEdit {{
    background: {palette.input_surface};
    border: 1px solid {palette.input_border};
    padding: 0 10px;
    color: {palette.text_primary};
    selection-background-color: {palette.accent};
    selection-color: {palette.accent_text};
}}

QLineEdit:hover,
QComboBox:hover,
QDateEdit:hover,
QSpinBox:hover,
QDoubleSpinBox:hover,
QPlainTextEdit:hover,
QTextEdit:hover {{
    border: 1px solid {palette.border_strong};
}}

QLineEdit:focus,
QComboBox:focus,
QDateEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QPlainTextEdit:focus,
QTextEdit:focus {{
    border: 1px solid {palette.input_focus};
    padding: 0 10px;
}}

/* ── ComboBox / DateEdit drop-down sub-control ────────────────────────── */

QComboBox::drop-down,
QDateEdit::drop-down {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 28px;
    background: transparent;
    border: none;
    border-left: 1px solid {palette.input_border};
    border-top-right-radius: {radius.small}px;
    border-bottom-right-radius: {radius.small}px;
}}

QComboBox:hover::drop-down,
QDateEdit:hover::drop-down {{
    border-left: 1px solid {palette.border_strong};
}}

QComboBox:focus::drop-down,
QDateEdit:focus::drop-down {{
    border-left: 1px solid {palette.input_focus};
}}

QComboBox::down-arrow,
QDateEdit::down-arrow {{
    width: 10px;
    height: 10px;
    image: none;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 5px solid {palette.text_muted};
}}

QComboBox:disabled::drop-down,
QDateEdit:disabled::drop-down {{
    border-left-color: {palette.border_default};
}}

/* ── SpinBox / DoubleSpinBox step buttons ─────────────────────────────── */

QSpinBox::up-button,
QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    background: transparent;
    border: none;
    border-left: 1px solid {palette.input_border};
    border-bottom: 1px solid {palette.input_border};
    border-top-right-radius: {radius.small}px;
}}

QSpinBox::down-button,
QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    background: transparent;
    border: none;
    border-left: 1px solid {palette.input_border};
    border-bottom-right-radius: {radius.small}px;
}}

QSpinBox:focus::up-button,
QDoubleSpinBox:focus::up-button,
QSpinBox:focus::down-button,
QDoubleSpinBox:focus::down-button {{
    border-left-color: {palette.input_focus};
}}

QSpinBox:focus::up-button,
QDoubleSpinBox:focus::up-button {{
    border-bottom-color: {palette.input_focus};
}}

QSpinBox::up-arrow,
QDoubleSpinBox::up-arrow {{
    width: 7px;
    height: 7px;
    image: none;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-bottom: 5px solid {palette.text_muted};
}}

QSpinBox::down-arrow,
QDoubleSpinBox::down-arrow {{
    width: 7px;
    height: 7px;
    image: none;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 5px solid {palette.text_muted};
}}

QSpinBox::up-button:hover,
QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover {{
    background: {palette.secondary_surface};
}}

QSpinBox::up-button:pressed,
QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed,
QDoubleSpinBox::down-button:pressed {{
    background: {palette.accent_soft};
}}

QSpinBox:disabled::up-button,
QDoubleSpinBox:disabled::up-button,
QSpinBox:disabled::down-button,
QDoubleSpinBox:disabled::down-button {{
    border-left-color: {palette.border_default};
    border-bottom-color: {palette.border_default};
}}

QTableView {{
    background: {palette.workspace_surface};
    alternate-background-color: {palette.secondary_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0;
    gridline-color: {palette.divider_subtle};
    selection-background-color: {palette.selected_fill};
    selection-color: {palette.selected_text};
    outline: 0;
}}

QTableView::item {{
    padding: 0 4px;
    border: none;
}}

QTableView::item:hover {{
    background: {palette.table_hover};
}}

QTableView::item:selected {{
    background: {palette.selected_fill};
    color: {palette.selected_text};
}}

QTableView::item:focus {{
    outline: none;
    border: none;
}}

QTreeView {{
    background: {palette.workspace_surface};
    alternate-background-color: {palette.secondary_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0;
    selection-background-color: {palette.selected_fill};
    selection-color: {palette.selected_text};
    outline: 0;
}}

QTreeView::item {{
    padding: 0 4px;
    border: none;
    min-height: {sizes.row_height_dense}px;
}}

QTreeView::item:hover {{
    background: {palette.table_hover};
}}

QTreeView::item:selected {{
    background: {palette.selected_fill};
    color: {palette.selected_text};
}}

QTreeView::item:focus {{
    outline: none;
    border: none;
}}

QHeaderView::section {{
    background: {palette.table_header};
    color: {palette.text_primary};
    border: none;
    border-right: 1px solid {palette.divider_subtle};
    border-bottom: 1px solid {palette.border_strong};
    padding: 0 6px;
    font-size: {typography.size_small}px;
    font-weight: {typography.weight_semibold};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 0 4px 0;
}}

QScrollBar::handle:vertical {{
    background: {palette.border_strong};
    min-height: 24px;
    border-radius: 5px;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
    height: 0px;
}}

QMenu {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    padding: 6px;
}}

QMenu::item {{
    padding: 8px 12px;
    border-radius: {radius.small}px;
}}

QMenu::item:selected {{
    background: {palette.accent_soft};
    color: {palette.accent};
}}

QToolTip {{
    background: {palette.raised_surface};
    color: {palette.text_primary};
    border: 1px solid {palette.border_default};
    padding: 6px 8px;
}}

/* ── QTabWidget — global tab styling ──────────────────────────────────── */

QTabWidget::pane {{
    background: {palette.workspace_surface};
    border: none;
    border-top: 1px solid {palette.border_default};
}}

QTabBar {{
    background: transparent;
}}

QTabBar::tab {{
    background: transparent;
    color: {palette.text_secondary};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 20px;
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_medium};
    min-width: 90px;
}}

QTabBar::tab:hover {{
    color: {palette.text_primary};
    background: {palette.accent_soft};
}}

QTabBar::tab:selected {{
    color: {palette.accent};
    font-weight: {typography.weight_semibold};
    border-bottom: 2px solid {palette.accent};
}}

QTabBar::tab:disabled {{
    color: {palette.disabled_text};
}}

/* ── Reporting workspace components ───────────────────────────────────── */

QFrame#ReportContextStrip {{
    background: {palette.workspace_surface};
    border-bottom: 1px solid {palette.divider_subtle};
    min-height: 44px;
    max-height: 44px;
}}

QFrame#ReportFilterBar {{
    background: {palette.raised_surface};
    border-bottom: 1px solid {palette.border_default};
    min-height: 50px;
    max-height: 50px;
}}

QFrame#ReportCanvasPlaceholder {{
    background: {palette.secondary_surface};
    border: 1px dashed {palette.border_default};
    border-radius: 0px;
}}

QFrame#PrintCanvasFrame,
QFrame#DrilldownFrame {{
    background: {palette.secondary_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

QFrame#ReportTileCard {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

QFrame#ReportTileCard:hover {{
    border-color: {palette.accent_soft_strong};
    background: {palette.accent_soft};
}}

QLabel#ReportTileTitle {{
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_primary};
}}

QLabel#ReportTileDesc {{
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
}}

QLabel#ReportTabSectionTitle {{
    font-size: {typography.size_section_title}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_primary};
}}

QLabel#ReportTabSubtitle {{
    color: {palette.text_secondary};
    font-size: {typography.size_body}px;
}}

QLabel#CanvasPlaceholderTitle {{
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_muted};
}}

QLabel#CanvasPlaceholderSub {{
    color: {palette.text_muted};
    font-size: {typography.size_dense}px;
}}

QFrame#AnalysisRatioCard,
QFrame#AnalysisInsightCard,
QFrame#AnalysisInterpretationPanel {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

QFrame#AnalysisRatioCard:hover,
QFrame#AnalysisInsightCard:hover {{
    border-color: {palette.accent_soft_strong};
    background: {palette.secondary_surface};
}}

QLabel#AnalysisSectionTitle {{
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_primary};
}}

QLabel#AnalysisSectionSubtitle,
QLabel#AnalysisInsightMeta,
QLabel#AnalysisMetricMeta {{
    color: {palette.text_secondary};
    font-size: {typography.size_dense}px;
}}

QLabel#AnalysisMetricLabel,
QLabel#AnalysisInsightTitle {{
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_semibold};
}}

QLabel#AnalysisMetricValue {{
    color: {palette.text_primary};
    font-size: {typography.size_section_title}px;
    font-weight: {typography.weight_semibold};
}}

QLabel#AnalysisInsightBody {{
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
}}

/* ── Command Palette ──────────────────────────────────────────────────── */

/* Overlay widget: must be fully transparent so paintEvent draws the dim */
QWidget#CommandPaletteOverlay {{
    background: transparent;
}}

QFrame#CommandPalette {{
    background: {palette.raised_surface};
    border: 1px solid {palette.border_strong};
    border-radius: {radius.medium}px;
}}

QLineEdit#CommandPaletteInput {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 8px 14px;
    font-size: 15px;
    font-weight: {typography.weight_medium};
    color: {palette.text_primary};
    selection-background-color: {palette.accent_soft_strong};
}}

QLineEdit#CommandPaletteInput:focus {{
    border: none;
    outline: none;
}}

QFrame#CommandPaletteSep {{
    background: {palette.border_default};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

QListWidget#CommandPaletteList {{
    background: transparent;
    border: none;
    padding: 4px 0;
    outline: none;
}}

QListWidget#CommandPaletteList::item {{
    background: transparent;
    border: none;
    padding: 0;
}}

QListWidget#CommandPaletteList::item:selected {{
    background: {palette.accent_soft};
    border-radius: {radius.small}px;
}}

QListWidget#CommandPaletteList::item:hover {{
    background: {palette.table_hover};
}}

QFrame#CommandPaletteHintBar {{
    background: {palette.secondary_surface};
    border-top: 1px solid {palette.border_default};
    border-bottom-left-radius: {radius.medium}px;
    border-bottom-right-radius: {radius.medium}px;
}}

QLabel#CommandPaletteHintLabel {{
    color: {palette.text_muted};
    font-size: 11px;
}}

/* ── Help Overlay ─────────────────────────────────────────────────────── */

QWidget#HelpOverlay {{
    background: transparent;
}}

QFrame#HelpPanel {{
    background: {palette.raised_surface};
    border: 1px solid {palette.border_strong};
    border-radius: {radius.medium}px;
}}

QFrame#HelpPanelHeader {{
    background: transparent;
    border: none;
}}

QLabel#HelpPanelTitle {{
    color: {palette.text_primary};
    font-size: 15px;
    font-weight: {typography.weight_semibold};
}}

QPushButton#HelpPanelClose {{
    background: transparent;
    border: none;
    border-radius: {radius.small}px;
    color: {palette.text_muted};
    font-size: 14px;
}}

QPushButton#HelpPanelClose:hover {{
    background: {palette.table_hover};
    color: {palette.text_primary};
}}

QFrame#HelpPanelSep {{
    background: {palette.border_default};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

QScrollArea#HelpPanelScroll {{
    background: transparent;
    border: none;
}}

QWidget#HelpPanelBodyContainer {{
    background: transparent;
}}

QLabel#HelpPanelSummary {{
    color: {palette.text_secondary};
    font-size: 13px;
    font-weight: {typography.weight_medium};
    padding-bottom: 4px;
}}

QLabel#HelpPanelBody {{
    color: {palette.text_primary};
    font-size: 13px;
    line-height: 1.5;
}}

QFrame#HelpPanelHintBar {{
    background: {palette.secondary_surface};
    border-top: 1px solid {palette.border_default};
    border-bottom-left-radius: {radius.medium}px;
    border-bottom-right-radius: {radius.medium}px;
}}

QLabel#HelpPanelHintLabel {{
    color: {palette.text_muted};
    font-size: 11px;
}}

/* ── Help Button (floating "?" on pages and dialogs) ──────────────────── */

QPushButton#HelpButton {{
    background: {palette.accent_soft};
    color: {palette.accent};
    border: 1px solid {palette.accent_soft_strong};
    border-radius: 16px;
    font-size: 14px;
    font-weight: {typography.weight_semibold};
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
}}

QPushButton#HelpButton:hover {{
    background: {palette.accent};
    color: {palette.raised_surface};
    border-color: {palette.accent};
}}

QPushButton#HelpButton:pressed {{
    background: {palette.accent_hover};
    color: {palette.raised_surface};
}}

/* ── User Profile Menu ──────────────────────────────────────── */

QFrame#UserProfileMenu {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: {radius.medium}px;
}}

QWidget#ProfileMenuHeader {{
    background: transparent;
}}

QLabel#ProfileMenuAvatar {{
    font-size: 14px;
    font-weight: 700;
    border-radius: 24px;
    min-width: 48px;
    min-height: 48px;
    max-width: 48px;
    max-height: 48px;
    padding: 0;
}}

QLabel#ProfileMenuAvatar[avatarMode="fallback"] {{
    background: {palette.accent_soft};
    border: 1px solid {palette.accent_soft_strong};
    color: {palette.accent};
}}

QLabel#ProfileMenuAvatar[avatarMode="image"] {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    color: transparent;
}}

QLabel#ProfileMenuName {{
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
    font-weight: 600;
}}

QLabel#ProfileMenuMeta {{
    color: {palette.text_muted};
    font-size: {typography.size_small}px;
}}

QPushButton#ProfileMenuAction {{
    text-align: left;
    padding: 7px 10px;
    border: none;
    border-radius: {radius.small}px;
    background: transparent;
    color: {palette.text_primary};
    font-size: {typography.size_body}px;
}}

QPushButton#ProfileMenuAction:hover {{
    background: {palette.accent_soft};
}}

QPushButton#ProfileMenuLogout {{
    text-align: left;
    padding: 7px 10px;
    border: none;
    border-radius: {radius.small}px;
    background: transparent;
    color: {palette.danger};
    font-size: {typography.size_body}px;
}}

QPushButton#ProfileMenuLogout:hover {{
    background: {palette.accent_soft};
}}

QFrame#ProfileMenuSeparator {{
    background: {palette.border_default};
    border: none;
    max-height: 1px;
    margin-left: 8px;
    margin-right: 8px;
}}

/* ── Entity Detail Workspaces (Phase 3) ─────────────────────── */

QWidget#EntityDetailPage,
QWidget#CustomerDetailPage,
QWidget#SupplierDetailPage,
QWidget#AccountDetailPage,
QWidget#ItemDetailPage {{
    background: {palette.workspace_surface};
}}

QFrame#EntityDetailHeader {{
    background: transparent;
    border: none;
}}

QLabel#EntityDetailTitle {{
    font-size: {typography.size_section_title}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_primary};
    padding: 0;
}}

QLabel#EntityDetailSubtitle {{
    font-size: {typography.size_small}px;
    color: {palette.text_secondary};
    padding: 0;
}}

QLabel#EntityDetailStatusChipActive {{
    background: {palette.success};
    color: #FFFFFF;
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_semibold};
    border-radius: 10px;
    padding: 2px 10px;
}}

QLabel#EntityDetailStatusChipInactive {{
    background: {palette.disabled_surface};
    color: {palette.disabled_text};
    font-size: {typography.size_caption}px;
    font-weight: {typography.weight_semibold};
    border-radius: 10px;
    padding: 2px 10px;
}}

QFrame#EntityDetailSeparator {{
    background: {palette.border_default};
    border: none;
    max-height: 1px;
}}

QPushButton#EntityDetailBackButton {{
    background: transparent;
    border: none;
    color: {palette.accent};
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_semibold};
    padding: 4px 0;
    text-align: left;
}}

QPushButton#EntityDetailBackButton:hover {{
    color: {palette.accent_hover};
    text-decoration: underline;
}}

/* Money Bar */

QFrame#MoneyBar {{
    background: transparent;
    border: none;
}}

QFrame#MoneyCardNeutral {{
    background: {palette.raised_surface};
    border: 1px solid {palette.border_default};
    border-top: 3px solid {palette.border_strong};
    border-radius: {radius.small}px;
    min-height: 58px;
}}

QFrame#MoneyCardDanger {{
    background: {palette.raised_surface};
    border: 1px solid {palette.border_default};
    border-top: 3px solid {palette.danger};
    border-radius: {radius.small}px;
    min-height: 58px;
}}

QFrame#MoneyCardWarning {{
    background: {palette.raised_surface};
    border: 1px solid {palette.border_default};
    border-top: 3px solid {palette.warning};
    border-radius: {radius.small}px;
    min-height: 58px;
}}

QFrame#MoneyCardSuccess {{
    background: {palette.raised_surface};
    border: 1px solid {palette.border_default};
    border-top: 3px solid {palette.success};
    border-radius: {radius.small}px;
    min-height: 58px;
}}

QFrame#MoneyCardInfo {{
    background: {palette.raised_surface};
    border: 1px solid {palette.border_default};
    border-top: 3px solid {palette.info};
    border-radius: {radius.small}px;
    min-height: 58px;
}}

QLabel#MoneyCardValue {{
    font-size: {typography.size_card_title}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_primary};
    background: transparent;
}}

QLabel#MoneyCardLabel {{
    font-size: {typography.size_caption}px;
    color: {palette.text_secondary};
    background: transparent;
}}

/* Entity Detail Tab Bar */

QTabBar#EntityDetailTabBar {{
    background: transparent;
}}

QTabBar#EntityDetailTabBar::tab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 16px;
    font-size: {typography.size_body}px;
    color: {palette.text_secondary};
    font-weight: {typography.weight_regular};
}}

QTabBar#EntityDetailTabBar::tab:selected {{
    color: {palette.accent};
    border-bottom: 2px solid {palette.accent};
    font-weight: {typography.weight_semibold};
}}

QTabBar#EntityDetailTabBar::tab:hover:!selected {{
    color: {palette.text_primary};
    border-bottom: 2px solid {palette.border_strong};
}}

/* Entity Info Tab */

QFrame#EntityInfoTab {{
    background: {palette.workspace_surface};
    border: 1px solid {palette.border_default};
    border-radius: 0px;
}}

QLabel#EntityInfoSectionTitle {{
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_secondary};
    padding-bottom: 4px;
}}

QLabel#EntityInfoLabel {{
    font-size: {typography.size_body}px;
    font-weight: {typography.weight_semibold};
    color: {palette.text_secondary};
}}

QLabel#EntityInfoValue {{
    font-size: {typography.size_body}px;
    color: {palette.text_primary};
}}

QFrame#EntityInfoSeparator {{
    background: {palette.border_default};
    border: none;
    max-height: 1px;
    margin: 4px 0;
}}
""".strip()
