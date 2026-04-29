"""Wizard state machine and orchestrator.

Drives a list of ``WizardStep`` instances through the explicit lifecycle:

    draft -> validated -> previewed -> committing -> committed | failed

The controller is UI-agnostic: it does not import Qt widgets. The host
dialog drives the controller and renders state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from seeker_accounting.platform.wizards.advisor import (
    AssistantEngine,
    WizardAdvisor,
)
from seeker_accounting.platform.wizards.context import WizardContext
from seeker_accounting.platform.wizards.state import WizardState
from seeker_accounting.platform.wizards.step import (
    StepValidationResult,
    WizardStep,
    WizardStepStatus,
)

logger = logging.getLogger("seeker_accounting.platform.wizards")


class WizardLifecycleStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PREVIEWED = "previewed"
    COMMITTING = "committing"
    COMMITTED = "committed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class StepCommitOutcome:
    success: bool
    error_message: str | None = None


class WizardController:
    """Drives a sequence of wizard steps with persistent state.

    The controller does not own persistence directly; the host injects a
    ``persist_callback`` invoked after every successful step transition so
    the wizard run record can be updated for resumability.
    """

    def __init__(
        self,
        *,
        wizard_code: str,
        steps: Iterable[WizardStep],
        context: WizardContext,
        state: WizardState | None = None,
        advisor: WizardAdvisor | None = None,
        assistant_engine: AssistantEngine | None = None,
    ) -> None:
        self._wizard_code = wizard_code
        self._steps: list[WizardStep] = list(steps)
        if not self._steps:
            raise ValueError("WizardController requires at least one step.")
        self._context = context
        self._state = state or WizardState()
        self._advisor = advisor
        self._assistant = assistant_engine or AssistantEngine()
        self._current_index = 0
        self._lifecycle = WizardLifecycleStatus.DRAFT

    # ── Read-only accessors ──────────────────────────────────────────────

    @property
    def wizard_code(self) -> str:
        return self._wizard_code

    @property
    def steps(self) -> list[WizardStep]:
        return list(self._steps)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def current_step(self) -> WizardStep:
        return self._steps[self._current_index]

    @property
    def state(self) -> WizardState:
        return self._state

    @property
    def context(self) -> WizardContext:
        return self._context

    @property
    def lifecycle(self) -> WizardLifecycleStatus:
        return self._lifecycle

    @property
    def advisor(self) -> WizardAdvisor | None:
        return self._advisor

    @property
    def assistant(self) -> AssistantEngine:
        return self._assistant

    @property
    def is_first(self) -> bool:
        return self._current_index == 0

    @property
    def is_last(self) -> bool:
        return self._current_index == len(self._steps) - 1

    # ── Navigation ───────────────────────────────────────────────────────

    def jump_to(self, index: int) -> None:
        if not 0 <= index < len(self._steps):
            raise IndexError(f"Step index {index} out of range.")
        self._current_index = index
        self._steps[self._current_index].status = WizardStepStatus.ACTIVE

    def back(self) -> None:
        if self._current_index <= 0:
            return
        self._current_index -= 1
        self._steps[self._current_index].status = WizardStepStatus.ACTIVE

    def advance(self) -> StepValidationResult:
        """Validate the current step, write back, optionally commit, then move forward.

        Steps that opt in via ``commits_on_advance = True`` have their
        ``commit()`` called immediately so subsequent steps can rely on the
        side effect (e.g. step 1 creates the company; step 2 needs its id).
        Other steps' commits are deferred to :meth:`commit_all` at finish.
        """
        step = self.current_step
        result = step.validate(self._context, self._state)
        if not result.is_valid:
            step.status = WizardStepStatus.FAILED
            return result
        step.write_back(self._state)
        if step.commits_on_advance:
            try:
                step.commit(self._context, self._state)
                step.status = WizardStepStatus.COMMITTED
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Wizard step '%s' failed during in-flight commit (wizard=%s).",
                    step.key,
                    self._wizard_code,
                )
                step.status = WizardStepStatus.FAILED
                return StepValidationResult.fail(
                    blocking=[f"This step could not be saved:\n{exc}"]
                )
        else:
            step.status = WizardStepStatus.VALIDATED
        if self._current_index < len(self._steps) - 1:
            self._current_index += 1
            self._steps[self._current_index].status = WizardStepStatus.ACTIVE
            # Auto-skip optional steps that opt out.
            self._auto_skip_optional()
        self._lifecycle = WizardLifecycleStatus.VALIDATED
        return result

    def _auto_skip_optional(self) -> None:
        while self._current_index < len(self._steps) - 1:
            step = self._steps[self._current_index]
            if not step.optional:
                return
            if not step.can_skip(self._context, self._state):
                return
            step.status = WizardStepStatus.SKIPPED
            self._current_index += 1
            self._steps[self._current_index].status = WizardStepStatus.ACTIVE

    # ── Commit ───────────────────────────────────────────────────────────

    def commit_all(self) -> StepCommitOutcome:
        """Commit every step that is not yet committed, in order.

        Each step's ``commit()`` is responsible for its own transactional
        boundary (most steps wrap a single service call which itself uses a
        unit of work). The controller calls them sequentially and stops on
        the first failure, leaving the wizard in ``FAILED`` lifecycle.
        """
        self._lifecycle = WizardLifecycleStatus.COMMITTING
        for step in self._steps:
            if step.status in (WizardStepStatus.COMMITTED, WizardStepStatus.SKIPPED):
                continue
            try:
                step.commit(self._context, self._state)
                step.status = WizardStepStatus.COMMITTED
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Wizard step '%s' failed during commit (wizard=%s).",
                    step.key,
                    self._wizard_code,
                )
                step.status = WizardStepStatus.FAILED
                self._lifecycle = WizardLifecycleStatus.FAILED
                return StepCommitOutcome(success=False, error_message=str(exc))
        self._lifecycle = WizardLifecycleStatus.COMMITTED
        return StepCommitOutcome(success=True)

    def cancel(self) -> None:
        self._lifecycle = WizardLifecycleStatus.CANCELLED

    # ── Advisor integration ──────────────────────────────────────────────

    def evaluate_advisor(self) -> list:
        return self._assistant.evaluate_step(
            self._advisor,
            self.current_step.key,
            self._context,
            self._state,
        )
