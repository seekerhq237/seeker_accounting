"""
Terminal output formatting for the license manager.

Provides clean, aligned table and detail output without external dependencies.
"""
from __future__ import annotations

import datetime
from typing import Sequence

from .ledger import LicenseRecord

# ── Box-drawing characters ────────────────────────────────────────────────────
_H = "\u2500"  # ─
_V = "\u2502"  # │
_TL = "\u250c"  # ┌
_TR = "\u2510"  # ┐
_BL = "\u2514"  # └
_BR = "\u2518"  # ┘
_LT = "\u251c"  # ├
_RT = "\u2524"  # ┤
_TT = "\u252c"  # ┬
_BT = "\u2534"  # ┴
_CR = "\u253c"  # ┼


def _status_label(record: LicenseRecord) -> str:
    today = datetime.date.today()
    if record.status == "revoked":
        return "REVOKED"
    try:
        expires = datetime.date.fromisoformat(record.expires_at)
        if expires < today:
            return "EXPIRED"
    except ValueError:
        pass
    return "ACTIVE"


def _edition_label(edition: int) -> str:
    return {1: "Standard"}.get(edition, f"Edition {edition}")


# ── Table rendering ──────────────────────────────────────────────────────────

_TABLE_COLUMNS = [
    ("ID", 5, "right"),
    ("Customer", 24, "left"),
    ("Email", 26, "left"),
    ("Edition", 10, "left"),
    ("Issued", 12, "left"),
    ("Expires", 12, "left"),
    ("Status", 9, "left"),
]


def _pad(text: str, width: int, align: str) -> str:
    if align == "right":
        return text.rjust(width)
    return text.ljust(width)


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + "\u2026"


def _row_line(cells: list[str], widths: list[int], aligns: list[str]) -> str:
    parts = []
    for cell, w, a in zip(cells, widths, aligns):
        parts.append(" " + _pad(_truncate(cell, w), w, a) + " ")
    return _V + _V.join(parts) + _V


def _border(widths: list[int], left: str, mid: str, right: str) -> str:
    segments = [_H * (w + 2) for w in widths]
    return left + mid.join(segments) + right


def format_table(records: Sequence[LicenseRecord]) -> str:
    """Render a list of license records as a clean ASCII table."""
    if not records:
        return "  No licenses found."

    names = [c[0] for c in _TABLE_COLUMNS]
    widths = [c[1] for c in _TABLE_COLUMNS]
    aligns = [c[2] for c in _TABLE_COLUMNS]

    lines: list[str] = []
    lines.append(_border(widths, _TL, _TT, _TR))
    lines.append(_row_line(names, widths, aligns))
    lines.append(_border(widths, _LT, _CR, _RT))

    for r in records:
        cells = [
            str(r.id),
            r.customer or "\u2014",
            r.email or "\u2014",
            _edition_label(r.edition),
            r.issued_at,
            r.expires_at,
            _status_label(r),
        ]
        lines.append(_row_line(cells, widths, aligns))

    lines.append(_border(widths, _BL, _BT, _BR))
    lines.append(f"  {len(records)} license(s)")
    return "\n".join(lines)


# ── Detail rendering ─────────────────────────────────────────────────────────

def format_detail(record: LicenseRecord) -> str:
    """Render a single license record as a detailed view."""
    status = _status_label(record)
    lines = [
        "",
        f"  License #{record.id}",
        f"  {'─' * 50}",
        f"  Customer   : {record.customer or '—'}",
        f"  Email      : {record.email or '—'}",
        f"  Edition    : {_edition_label(record.edition)}",
        f"  Issued     : {record.issued_at}",
        f"  Expires    : {record.expires_at}",
        f"  Status     : {status}",
    ]
    if record.revoked_at:
        lines.append(f"  Revoked at : {record.revoked_at}")
    if record.notes:
        lines.append(f"  Notes      : {record.notes}")
    lines.append(f"  {'─' * 50}")
    lines.append(f"  Key        : {record.key}")
    lines.append("")
    return "\n".join(lines)


# ── Key display ──────────────────────────────────────────────────────────────

def format_issued_key(
    record: LicenseRecord,
    *,
    show_copy_hint: bool = True,
) -> str:
    """Format the output shown immediately after issuing a new key."""
    lines = [
        "",
        "  ══════════════════════════════════════════════════════",
        "   LICENSE KEY ISSUED",
        "  ══════════════════════════════════════════════════════",
        f"   ID        : #{record.id}",
        f"   Customer  : {record.customer or '—'}",
        f"   Email     : {record.email or '—'}",
        f"   Edition   : {_edition_label(record.edition)}",
        f"   Issued    : {record.issued_at}",
        f"   Expires   : {record.expires_at}",
        "  ──────────────────────────────────────────────────────",
        "",
        f"   {record.key}",
        "",
        f"   Key length: {len(record.key)} characters",
        "  ══════════════════════════════════════════════════════",
    ]
    if show_copy_hint:
        lines.append("")
        lines.append(f"   Export to file:  python -m tools.license_manager export {record.id}")
    lines.append("")
    return "\n".join(lines)


# ── Verification display ────────────────────────────────────────────────────

def format_verification(
    key_string: str,
    edition: int,
    issued_at: datetime.date,
    expires_at: datetime.date,
) -> str:
    """Format the output for a successful key verification."""
    today = datetime.date.today()
    remaining = (expires_at - today).days
    if remaining < 0:
        status = f"EXPIRED ({-remaining} day(s) ago)"
    elif remaining == 0:
        status = "EXPIRES TODAY"
    else:
        status = f"VALID ({remaining} day(s) remaining)"

    lines = [
        "",
        "  ✓ Signature verified — key is authentic.",
        "",
        f"    Edition  : {_edition_label(edition)}",
        f"    Issued   : {issued_at.isoformat()}",
        f"    Expires  : {expires_at.isoformat()}",
        f"    Status   : {status}",
        "",
    ]
    return "\n".join(lines)
