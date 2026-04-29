"""Advisor for the COA Customization Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.coa_customization import state_keys as K
from seeker_accounting.modules.wizards.coa_customization.steps.confirm_step import (
    _diff_role_changes,
)
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)

# Roles that block major workflows when unmapped.
CRITICAL_ROLES = {
    "ar_control": "AR Control",
    "ap_control": "AP Control",
    "vat_input": "VAT Input",
    "vat_output": "VAT Output",
    "retained_earnings": "Retained Earnings",
}


def _baseline_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    if not state.get(K.KEY_APPLY_BASELINE) and not state.get(K.KEY_BASELINE_APPLIED):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Consider applying the OHADA baseline",
                detail="The OHADA SYSCOHADA chart is the standard starting point and only inserts missing accounts; existing accounts are preserved.",
            )
        )
    return msgs


def _role_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    selections = state.get(K.KEY_ROLE_SELECTIONS) or {}
    current = state.get(K.KEY_ROLE_CURRENT) or {}
    for role_code, label in CRITICAL_ROLES.items():
        sel = selections.get(role_code) if role_code in selections else current.get(role_code)
        if not isinstance(sel, int):
            msgs.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.WARNING,
                    title=f"Critical role unmapped: {label}",
                    detail=f"The role {role_code!r} has no account assigned. Workflows that depend on it (postings, allocations, closing) will fail until it is mapped.",
                )
            )
    return msgs


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    to_set, to_clear = _diff_role_changes(state)
    msgs: list[AdvisorMessage] = []
    if not to_set and not to_clear and not state.get(K.KEY_BASELINE_APPLIED):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="No changes to persist",
                detail="No role mapping changes were made and the baseline was not applied. The wizard will close without changes.",
            )
        )
    if to_clear:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Clearing role mappings",
                detail=f"{len(to_clear)} role mapping(s) will be cleared. Workflows depending on those roles will start failing.",
            )
        )
    return msgs


def build_coa_customization_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="coa_customization")
    advisor.register("baseline", _baseline_rules)
    advisor.register("role_mapping", _role_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
