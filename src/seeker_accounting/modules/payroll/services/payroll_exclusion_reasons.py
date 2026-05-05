"""Structured exclusion-reason taxonomy for payroll runs (P3.S6).

The legacy cockpit captured exclusion reasons as free text. This module
defines a small canonical taxonomy that the UI uses to render a reason
picker; the resulting persisted ``exclusion_reason`` is a structured
prefix (``code: free text``) so existing free-text storage stays
backwards compatible without a schema change.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class ExclusionReasonCode(str, Enum):
    """Canonical reason codes for excluding an employee from a run."""

    TERMINATED_MID_PERIOD = "terminated_mid_period"
    UNPAID_LEAVE = "unpaid_leave"
    DISPUTE = "dispute"
    OFF_CYCLE = "off_cycle"
    NEW_HIRE_NOT_READY = "new_hire_not_ready"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ExclusionReasonChoice:
    code: ExclusionReasonCode
    label: str
    requires_note: bool
    description: str = ""


REASON_CHOICES: Final[tuple[ExclusionReasonChoice, ...]] = (
    ExclusionReasonChoice(
        code=ExclusionReasonCode.TERMINATED_MID_PERIOD,
        label="Terminated mid-period",
        requires_note=False,
        description="Employee left before the end of the run period.",
    ),
    ExclusionReasonChoice(
        code=ExclusionReasonCode.UNPAID_LEAVE,
        label="On unpaid leave",
        requires_note=False,
    ),
    ExclusionReasonChoice(
        code=ExclusionReasonCode.DISPUTE,
        label="Pay dispute / under review",
        requires_note=True,
        description="A free-text note is required to document the dispute.",
    ),
    ExclusionReasonChoice(
        code=ExclusionReasonCode.OFF_CYCLE,
        label="Paid off-cycle",
        requires_note=False,
    ),
    ExclusionReasonChoice(
        code=ExclusionReasonCode.NEW_HIRE_NOT_READY,
        label="New hire — payroll setup incomplete",
        requires_note=False,
    ),
    ExclusionReasonChoice(
        code=ExclusionReasonCode.OTHER,
        label="Other",
        requires_note=True,
        description="A free-text explanation is required.",
    ),
)


_LABEL_BY_CODE: Final[dict[str, str]] = {
    c.code.value: c.label for c in REASON_CHOICES
}


def format_reason(code: ExclusionReasonCode | str, note: str | None) -> str:
    """Combine a reason code and optional note into a single stored string.

    Format: ``"<code>: <note>"`` if a note is provided, else just
    ``"<code>"``. The structured prefix lets future migrations split the
    column without losing information.
    """
    raw = code.value if isinstance(code, ExclusionReasonCode) else str(code)
    note = (note or "").strip()
    if note:
        return f"{raw}: {note}"
    return raw


def parse_reason(stored: str | None) -> tuple[str | None, str]:
    """Split a stored ``exclusion_reason`` into ``(code, note)``.

    Returns ``(None, "")`` for empty input, ``(None, stored)`` for a
    stored value that does not match the structured prefix (legacy free
    text).
    """
    if not stored:
        return None, ""
    s = stored.strip()
    head, sep, tail = s.partition(":")
    head_key = head.strip()
    if sep and head_key in _LABEL_BY_CODE:
        return head_key, tail.strip()
    # Recognise bare code with no separator (we sometimes write that).
    if head_key in _LABEL_BY_CODE and not sep:
        return head_key, ""
    return None, s


def reason_label(stored: str | None) -> str:
    """Human-readable label for a stored reason."""
    code, note = parse_reason(stored)
    if code is not None:
        label = _LABEL_BY_CODE.get(code, code)
        return f"{label} — {note}" if note else label
    return stored or ""
