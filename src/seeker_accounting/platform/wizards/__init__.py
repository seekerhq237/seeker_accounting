"""Platform wizard framework.

Provides the building blocks for service-driven, stateful, resumable wizards:

- ``WizardState``        — serializable state bag persisted between steps
- ``WizardStep``         — abstract step with validate/preview/commit hooks
- ``WizardController``   — orchestrates a sequence of steps and a state machine
- ``WizardContext``      — runtime services + scope handed to every step
- ``AssistantEngine``    — pluggable advisor (suggestions, validations, anomalies)
- ``WizardAdvisor``      — base class for per-wizard advisor rule packs
- ``WizardHostDialog``   — Qt host dialog rendering the framework consistently

See ``docs/Wizards.md`` for the architectural contract.
"""
from seeker_accounting.platform.wizards.advisor import (
    AdvisorMessage,
    AdvisorSeverity,
    AssistantEngine,
    WizardAdvisor,
)
from seeker_accounting.platform.wizards.context import WizardContext
from seeker_accounting.platform.wizards.controller import (
    WizardController,
    WizardLifecycleStatus,
)
from seeker_accounting.platform.wizards.launcher import (
    WizardOutcome,
    launch_wizard,
    require_active_company,
    resolve_active_company_id,
    resolve_user_id,
    run_wizard,
)
from seeker_accounting.platform.wizards.state import WizardState
from seeker_accounting.platform.wizards.step import (
    StepValidationResult,
    WizardStep,
    WizardStepStatus,
)

__all__ = [
    "AdvisorMessage",
    "AdvisorSeverity",
    "AssistantEngine",
    "WizardAdvisor",
    "WizardContext",
    "WizardController",
    "WizardLifecycleStatus",
    "WizardOutcome",
    "WizardState",
    "WizardStep",
    "WizardStepStatus",
    "StepValidationResult",
    "launch_wizard",
    "require_active_company",
    "resolve_active_company_id",
    "resolve_user_id",
    "run_wizard",
]
