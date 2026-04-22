"""Payroll-specific exceptions for actionable operator feedback.

These extend the base ValidationError so existing UI catch blocks continue
to work, while adding structured context about what went wrong and how
to fix it.
"""
from __future__ import annotations

from seeker_accounting.platform.exceptions import ValidationError


class PayrollSetupError(ValidationError):
    """Raised when payroll setup is incomplete for the requested operation."""


class MissingAccountMappingError(ValidationError):
    """Raised when a payroll component lacks the required expense/liability account."""

    def __init__(self, component_code: str, mapping_type: str) -> None:
        self.component_code = component_code
        self.mapping_type = mapping_type
        super().__init__(
            f"Component '{component_code}' has no {mapping_type} account mapped. "
            f"Configure it in Payroll Setup > Components before proceeding."
        )


class MissingRuleSetError(ValidationError):
    """Raised when a rule-based component has no effective rule set."""

    def __init__(self, component_code: str, rule_code: str) -> None:
        self.component_code = component_code
        self.rule_code = rule_code
        super().__init__(
            f"Component '{component_code}' requires rule set '{rule_code}' but "
            f"no effective rule set was found. Apply a statutory pack or create "
            f"the rule set manually."
        )


class PayrollRunStateError(ValidationError):
    """Raised when a payroll run is in the wrong state for the requested action."""

    def __init__(self, run_reference: str, current_status: str, required_status: str) -> None:
        self.run_reference = run_reference
        self.current_status = current_status
        self.required_status = required_status
        super().__init__(
            f"Run '{run_reference}' is in status '{current_status}'. "
            f"Required: '{required_status}'."
        )


class ProvisionalFallbackWarning:
    """Not an exception — a structured warning when a provisional fallback constant
    was used instead of a configured rule set.  Collected during calculation and
    surfaced in validation/dashboard."""

    def __init__(self, component_code: str, fallback_description: str) -> None:
        self.component_code = component_code
        self.fallback_description = fallback_description

    def __str__(self) -> str:
        return (
            f"Component '{self.component_code}' used provisional fallback: "
            f"{self.fallback_description}. Configure the matching rule set for "
            f"production accuracy."
        )
