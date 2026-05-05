"""Canonical payroll-run state machine (Phase 3 / Slice P3.S1).

The truth-of-record for state transitions still lives in
:class:`PayrollRunService` — every transition is performed there with audit
logging, repository writes, and concurrency guards.

This module is the *descriptive* counterpart used by the UI cockpit:

* derive button enablement (Calculate / Approve / Void / Post / Reverse)
* describe the canonical primary action for the current state
* render the timeline of states the run can move through
* present human-readable labels via :class:`CodeLabelRegistry`

It is intentionally pure: no ORM, no service registry, no Qt. Anything
that needs a database or audit log belongs in the service.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, FrozenSet


class PayrollRunStatus(str, Enum):
    """Status codes persisted on :class:`PayrollRun.status_code`.

    Values match the DB column exactly so the enum can be compared
    directly against ``run.status_code``.
    """

    DRAFT = "draft"
    CALCULATED = "calculated"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    APPROVED = "approved"
    POSTED = "posted"
    REVERSED = "reversed"
    VOIDED = "voided"


_TERMINAL: Final[frozenset[str]] = frozenset({
    PayrollRunStatus.REVERSED.value,
    PayrollRunStatus.VOIDED.value,
})


# Allowed forward transitions. ``calculated -> calculated`` represents a
# recalculation (clears prior employee rows and re-runs the engines).
_ALLOWED: Final[dict[str, frozenset[str]]] = {
    PayrollRunStatus.DRAFT.value: frozenset({
        PayrollRunStatus.CALCULATED.value,
        PayrollRunStatus.VOIDED.value,
    }),
    PayrollRunStatus.CALCULATED.value: frozenset({
        PayrollRunStatus.CALCULATED.value,  # recalc
        PayrollRunStatus.SUBMITTED_FOR_REVIEW.value,
        PayrollRunStatus.APPROVED.value,
        PayrollRunStatus.VOIDED.value,
    }),
    PayrollRunStatus.SUBMITTED_FOR_REVIEW.value: frozenset({
        PayrollRunStatus.CALCULATED.value,   # sent back
        PayrollRunStatus.APPROVED.value,
    }),
    PayrollRunStatus.APPROVED.value: frozenset({
        PayrollRunStatus.POSTED.value,
    }),
    PayrollRunStatus.POSTED.value: frozenset({
        PayrollRunStatus.REVERSED.value,
    }),
    PayrollRunStatus.REVERSED.value: frozenset(),
    PayrollRunStatus.VOIDED.value: frozenset(),
}


# Canonical timeline shown in the cockpit header. Branches (voided,
# reversed) are rendered as side-states off the main path.
TIMELINE_ORDER: Final[tuple[str, ...]] = (
    PayrollRunStatus.DRAFT.value,
    PayrollRunStatus.CALCULATED.value,
    PayrollRunStatus.SUBMITTED_FOR_REVIEW.value,
    PayrollRunStatus.APPROVED.value,
    PayrollRunStatus.POSTED.value,
)

SIDE_STATES: Final[tuple[str, ...]] = (
    PayrollRunStatus.VOIDED.value,
    PayrollRunStatus.REVERSED.value,
)


# Human-readable labels. Kept here (not in the service) because the UI
# cockpit and tests both consume them.
STATUS_LABELS: Final[dict[str, str]] = {
    PayrollRunStatus.DRAFT.value: "Draft",
    PayrollRunStatus.CALCULATED.value: "Calculated",
    PayrollRunStatus.SUBMITTED_FOR_REVIEW.value: "In Review",
    PayrollRunStatus.APPROVED.value: "Approved",
    PayrollRunStatus.POSTED.value: "Posted",
    PayrollRunStatus.REVERSED.value: "Reversed",
    PayrollRunStatus.VOIDED.value: "Voided",
}


@dataclass(frozen=True, slots=True)
class PrimaryAction:
    """Describes the cockpit's primary action button for a given state."""

    command_id: str
    label: str
    target_state: str
    is_destructive: bool = False


_PRIMARY_BY_STATE: Final[dict[str, PrimaryAction]] = {
    PayrollRunStatus.DRAFT.value: PrimaryAction(
        command_id="payroll.run.calculate",
        label="Calculate",
        target_state=PayrollRunStatus.CALCULATED.value,
    ),
    PayrollRunStatus.CALCULATED.value: PrimaryAction(
        command_id="payroll.run.approve",
        label="Approve",
        target_state=PayrollRunStatus.APPROVED.value,
    ),
    PayrollRunStatus.SUBMITTED_FOR_REVIEW.value: PrimaryAction(
        command_id="payroll.run.approve",
        label="Approve",
        target_state=PayrollRunStatus.APPROVED.value,
    ),
    PayrollRunStatus.APPROVED.value: PrimaryAction(
        command_id="payroll.run.post",
        label="Post to GL",
        target_state=PayrollRunStatus.POSTED.value,
    ),
    PayrollRunStatus.POSTED.value: PrimaryAction(
        command_id="payroll.run.reverse",
        label="Reverse",
        target_state=PayrollRunStatus.REVERSED.value,
        is_destructive=True,
    ),
}


class PayrollRunStateMachine:
    """Pure descriptive helpers around payroll-run state transitions."""

    # ── transition queries ────────────────────────────────────────────

    @staticmethod
    def is_terminal(status: str) -> bool:
        return status in _TERMINAL

    @staticmethod
    def allowed_transitions(status: str) -> FrozenSet[str]:
        return _ALLOWED.get(status, frozenset())

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        return target in cls.allowed_transitions(current)

    # ── action gating used by the cockpit UI ──────────────────────────

    @classmethod
    def can_calculate(cls, status: str) -> bool:
        """True when Calculate / Recalculate is allowed."""
        return status in (
            PayrollRunStatus.DRAFT.value,
            PayrollRunStatus.CALCULATED.value,
        )

    @classmethod
    def can_approve(cls, status: str) -> bool:
        return status == PayrollRunStatus.CALCULATED.value

    @classmethod
    def can_void(cls, status: str) -> bool:
        return status in (
            PayrollRunStatus.DRAFT.value,
            PayrollRunStatus.CALCULATED.value,
        )

    @classmethod
    def can_post(cls, status: str) -> bool:
        return status == PayrollRunStatus.APPROVED.value

    @classmethod
    def can_reverse(cls, status: str) -> bool:
        return status == PayrollRunStatus.POSTED.value

    @classmethod
    def can_edit_inclusion(cls, status: str) -> bool:
        """Employee include/exclude is only mutable on a calculated run."""
        return status == PayrollRunStatus.CALCULATED.value

    @classmethod
    def is_immutable(cls, status: str) -> bool:
        """Posted / reversed runs are immutable for accounting purposes."""
        return status in (
            PayrollRunStatus.POSTED.value,
            PayrollRunStatus.REVERSED.value,
        )

    # ── presentation helpers ──────────────────────────────────────────

    @staticmethod
    def status_label(status: str) -> str:
        return STATUS_LABELS.get(status, status.replace("_", " ").title())

    @staticmethod
    def primary_action(status: str) -> PrimaryAction | None:
        return _PRIMARY_BY_STATE.get(status)


__all__ = [
    "PayrollRunStatus",
    "PayrollRunStateMachine",
    "PrimaryAction",
    "STATUS_LABELS",
    "TIMELINE_ORDER",
    "SIDE_STATES",
]
