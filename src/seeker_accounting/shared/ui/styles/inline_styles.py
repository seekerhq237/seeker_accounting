from __future__ import annotations

from seeker_accounting.shared.ui.styles.palette import LIGHT_PALETTE as _P


_STATUS_FAMILIES = {
    "success": (_P.status_success_bg, _P.status_success_fg, _P.status_success_border),
    "warning": (_P.status_warning_bg, _P.status_warning_fg, _P.status_warning_border),
    "danger": (_P.status_danger_bg, _P.status_danger_fg, _P.status_danger_border),
    "info": (_P.status_info_bg, _P.status_info_fg, _P.status_info_border),
    "neutral": (_P.status_neutral_bg, _P.status_neutral_fg, _P.status_neutral_border),
    "accent": (_P.status_accent_bg, _P.status_accent_fg, _P.status_accent_border),
}

_TEXT_ROLES = {
    "primary": _P.text_primary,
    "secondary": _P.text_secondary,
    "muted": _P.text_muted,
    "success": _P.status_success_fg,
    "warning": _P.status_warning_fg,
    "danger": _P.status_danger_fg,
    "info": _P.status_info_fg,
    "accent": _P.status_accent_fg,
}


def text_style(
    role: str = "primary",
    *,
    font_size: str | None = None,
    font_weight: str | int | None = None,
    extra: str | None = None,
) -> str:
    parts = [f"color: {_TEXT_ROLES.get(role, _P.text_primary)};"]
    if font_size:
        parts.append(f"font-size: {font_size};")
    if font_weight:
        parts.append(f"font-weight: {font_weight};")
    if extra:
        parts.append(extra.rstrip(";") + ";")
    return " ".join(parts)


def status_chip_style(
    family: str,
    *,
    padding: str = "2px 10px",
    radius: int = 2,
    font_weight: str | int = 600,
    border: bool = True,
) -> str:
    bg, fg, outline = _STATUS_FAMILIES.get(family, _STATUS_FAMILIES["neutral"])
    parts = [
        f"background: {bg};",
        f"color: {fg};",
        f"padding: {padding};",
        f"border-radius: {radius}px;",
        f"font-weight: {font_weight};",
    ]
    if border:
        parts.append(f"border: 1px solid {outline};")
    return " ".join(parts)


def panel_style(family: str = "neutral", *, left_border: bool = False) -> str:
    bg, fg, outline = _STATUS_FAMILIES.get(family, _STATUS_FAMILIES["neutral"])
    border = f"border-left: 3px solid {outline};" if left_border else f"border: 1px solid {outline};"
    return f"background-color: {bg}; color: {fg}; {border}"


def line_edit_style() -> str:
    return (
        f"QLineEdit {{ border: 1px solid {_P.input_border}; border-radius: 4px; "
        f"padding: 0 10px; font-size: 13px; color: {_P.text_primary}; "
        f"background: {_P.input_surface}; }}"
        f"QLineEdit:focus {{ border-color: {_P.input_focus}; background: {_P.workspace_surface}; }}"
    )


def solid_button_style(family: str = "accent") -> str:
    bg = {
        "accent": _P.accent,
        "success": _P.success,
        "danger": _P.danger,
        "warning": _P.warning,
        "neutral": _P.text_secondary,
    }.get(family, _P.accent)
    hover = {
        "accent": _P.accent_hover,
        "success": _P.status_success_fg,
        "danger": _P.status_danger_fg,
        "warning": _P.status_warning_fg,
        "neutral": _P.text_primary,
    }.get(family, _P.accent_hover)
    return (
        f"QPushButton {{ background: {bg}; color: {_P.accent_text}; border: none; "
        "border-radius: 4px; padding: 0 12px; font-size: 12px; font-weight: 600; }}"
        f"QPushButton:hover {{ background: {hover}; }}"
    )


def ghost_button_style() -> str:
    return (
        f"QPushButton {{ background: transparent; border: 1px solid {_P.border_default}; "
        f"border-radius: 4px; padding: 0 12px; font-size: 12px; color: {_P.text_secondary}; }}"
        f"QPushButton:hover {{ background: {_P.command_bar_button_hover}; }}"
    )