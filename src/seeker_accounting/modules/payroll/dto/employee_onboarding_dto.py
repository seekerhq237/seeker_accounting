"""Phase 4 Hire-to-Pay BP DTOs and state machine.

The employee onboarding business process is owned by
:class:`EmployeeOnboardingService`. This module provides:

* :class:`EmployeeOnboardingState` — canonical state codes.
* :class:`EmployeeOnboardingStep` — canonical step codes (subset of
  state codes that represent in-progress drafting).
* :class:`EmployeeOnboardingDraftDTO` — read-side snapshot.
* :class:`EmployeeOnboardingStartCommand`,
  :class:`EmployeeOnboardingStepUpdate`,
  :class:`EmployeeOnboardingCompletion` — write-side commands.

Following the project's hardline accounting/portability rules, the BP
deliberately does **not** mutate ``employees`` until the
``review`` step is finalised. Until then the entire draft lives in
``employee_onboarding_drafts.payload_json``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


# ── State machine ────────────────────────────────────────────────────────


class EmployeeOnboardingState(StrEnum):
    """Canonical state codes for the Hire-to-Pay BP.

    Forward order (preparer view):

    ``draft_identity → draft_employment → draft_compensation
     → draft_payment → draft_statutory → draft_components
     → draft_review → completed``

    Backward jumps within drafting are permitted (the user can revise
    earlier steps from review). ``abandoned`` is a terminal state that
    can be reached from any drafting step.
    """

    DRAFT_IDENTITY = "draft_identity"
    DRAFT_EMPLOYMENT = "draft_employment"
    DRAFT_COMPENSATION = "draft_compensation"
    DRAFT_PAYMENT = "draft_payment"
    DRAFT_STATUTORY = "draft_statutory"
    DRAFT_COMPONENTS = "draft_components"
    DRAFT_REVIEW = "draft_review"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# Linear ordering of drafting steps. Used to validate forward
# transitions and to compute "next step" / "previous step".
DRAFTING_STEP_ORDER: tuple[EmployeeOnboardingState, ...] = (
    EmployeeOnboardingState.DRAFT_IDENTITY,
    EmployeeOnboardingState.DRAFT_EMPLOYMENT,
    EmployeeOnboardingState.DRAFT_COMPENSATION,
    EmployeeOnboardingState.DRAFT_PAYMENT,
    EmployeeOnboardingState.DRAFT_STATUTORY,
    EmployeeOnboardingState.DRAFT_COMPONENTS,
    EmployeeOnboardingState.DRAFT_REVIEW,
)

DRAFTING_STEP_CODES: frozenset[str] = frozenset(s.value for s in DRAFTING_STEP_ORDER)
TERMINAL_STATES: frozenset[str] = frozenset(
    {EmployeeOnboardingState.COMPLETED.value, EmployeeOnboardingState.ABANDONED.value}
)


# Step keys used inside ``payload_json`` for each step's collected
# fields. Keeping these distinct from state codes lets us evolve UI
# step grouping without breaking persisted drafts.
STEP_PAYLOAD_KEYS: tuple[str, ...] = (
    "identity",
    "employment",
    "compensation",
    "payment",
    "statutory",
    "components",
)

STATE_TO_PAYLOAD_KEY: dict[str, str] = {
    EmployeeOnboardingState.DRAFT_IDENTITY.value: "identity",
    EmployeeOnboardingState.DRAFT_EMPLOYMENT.value: "employment",
    EmployeeOnboardingState.DRAFT_COMPENSATION.value: "compensation",
    EmployeeOnboardingState.DRAFT_PAYMENT.value: "payment",
    EmployeeOnboardingState.DRAFT_STATUTORY.value: "statutory",
    EmployeeOnboardingState.DRAFT_COMPONENTS.value: "components",
}


def is_drafting(state_code: str) -> bool:
    return state_code in DRAFTING_STEP_CODES


def is_terminal(state_code: str) -> bool:
    return state_code in TERMINAL_STATES


def next_drafting_state(current: str) -> str | None:
    """Return the next drafting state, or ``None`` if at review."""
    try:
        idx = [s.value for s in DRAFTING_STEP_ORDER].index(current)
    except ValueError:
        return None
    if idx + 1 >= len(DRAFTING_STEP_ORDER):
        return None
    return DRAFTING_STEP_ORDER[idx + 1].value


def previous_drafting_state(current: str) -> str | None:
    """Return the previous drafting state, or ``None`` if at first step."""
    try:
        idx = [s.value for s in DRAFTING_STEP_ORDER].index(current)
    except ValueError:
        return None
    if idx == 0:
        return None
    return DRAFTING_STEP_ORDER[idx - 1].value


# ── Read DTOs ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EmployeeOnboardingDraftDTO:
    """Snapshot of a single draft."""

    id: int
    company_id: int
    status_code: str
    current_step: str
    payload: Mapping[str, Any]
    started_by_user_id: int | None
    last_modified_by_user_id: int | None
    completed_at: datetime | None
    abandoned_at: datetime | None
    abandon_reason: str | None
    produced_employee_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


# ── Write commands ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EmployeeOnboardingStartCommand:
    company_id: int
    started_by_user_id: int | None = None
    initial_payload: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class EmployeeOnboardingStepUpdate:
    """Patch the payload for a single step.

    ``step_code`` must be one of ``STEP_PAYLOAD_KEYS``. ``patch``
    replaces the matching slot wholesale (callers should send a full
    step object, not a delta).
    """

    draft_id: int
    step_code: str
    patch: Mapping[str, Any]
    actor_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class EmployeeOnboardingTransition:
    draft_id: int
    target_state: str  # one of EmployeeOnboardingState values
    actor_user_id: int | None = None
    abandon_reason: str | None = None
