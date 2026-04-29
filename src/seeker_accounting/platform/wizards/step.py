"""Abstract wizard step contract.

Each step is a small, service-driven orchestration with explicit hooks:

- ``build_widget()``  — produce the Qt widget the host displays
- ``load(context, state)`` — pre-fill from context & prior step state
- ``validate(context, state)`` — return ``StepValidationResult``
- ``preview(context, state)`` — optional dry-run summary for review/confirm steps
- ``commit(context, state)`` — actually perform the side effect
- ``write_back(state)`` — push collected values into the wizard state

UI work happens in ``build_widget``/``load`` only. All business decisions and
side effects MUST go through services in ``validate``/``preview``/``commit``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from seeker_accounting.platform.wizards.context import WizardContext
    from seeker_accounting.platform.wizards.state import WizardState


class WizardStepStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    VALIDATED = "validated"
    COMMITTED = "committed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True)
class StepValidationResult:
    """Outcome of a step's ``validate()`` call."""

    is_valid: bool
    field_errors: dict[str, str] = field(default_factory=dict)
    blocking_messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls) -> "StepValidationResult":
        return cls(is_valid=True)

    @classmethod
    def fail(
        cls,
        *,
        field_errors: dict[str, str] | None = None,
        blocking: list[str] | None = None,
    ) -> "StepValidationResult":
        return cls(
            is_valid=False,
            field_errors=dict(field_errors or {}),
            blocking_messages=list(blocking or []),
        )


class WizardStep:
    """Base class for wizard steps.

    Subclasses should override the hooks they need. The default implementations
    are deliberately permissive (no-op validate, no-op commit) so that purely
    informational or review steps remain trivial to write.
    """

    #: Stable step key used in the state bag and in persisted run state.
    key: str = ""

    #: Short label shown in the wizard's left rail.
    title: str = ""

    #: One-line subtitle shown under the rail title.
    subtitle: str = ""

    #: When True, the framework auto-advances past this step if ``can_skip``
    #: returns True (e.g., baseline data already configured).
    optional: bool = False

    #: When True, the controller calls ``commit()`` on this step as part of
    #: ``advance()`` (after a successful ``validate``), so later steps can
    #: rely on the side effect. When False, ``commit()`` is deferred to
    #: ``WizardController.commit_all()`` at finish.
    commits_on_advance: bool = False

    def __init__(self) -> None:
        self._widget: QWidget | None = None
        self.status: WizardStepStatus = WizardStepStatus.PENDING

    # ── Lifecycle hooks ───────────────────────────────────────────────────

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        """Construct (or return cached) the widget shown for this step.

        Subclasses MUST override.
        """
        raise NotImplementedError

    def load(self, context: "WizardContext", state: "WizardState") -> None:  # noqa: B027
        """Populate the widget from context + prior state. Default: no-op."""

    def can_skip(self, context: "WizardContext", state: "WizardState") -> bool:  # noqa: ARG002
        """Return True to skip this step entirely (only honored when ``optional``)."""
        return False

    def validate(self, context: "WizardContext", state: "WizardState") -> StepValidationResult:  # noqa: ARG002
        """Validate the current widget input. Default: pass."""
        return StepValidationResult.ok()

    def preview(self, context: "WizardContext", state: "WizardState") -> str | None:  # noqa: ARG002
        """Return a plain-language preview of side effects, or ``None``."""
        return None

    def commit(self, context: "WizardContext", state: "WizardState") -> None:  # noqa: B027,ARG002
        """Perform the actual side effect via services. Default: no-op."""

    def write_back(self, state: "WizardState") -> None:  # noqa: B027,ARG002
        """Copy collected widget values back into the shared state bag.

        Called automatically after a successful ``validate``. Default: no-op.
        """

    # ── Convenience ───────────────────────────────────────────────────────

    @property
    def widget(self) -> QWidget | None:
        return self._widget

    def _set_widget(self, widget: QWidget) -> None:
        self._widget = widget
