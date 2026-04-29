"""Advisor for the User Provisioning Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.user_provisioning import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _identity_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    pwd = state.get(K.KEY_PASSWORD) or ""
    if pwd and len(pwd) < 12:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Use a longer password",
                detail="Initial passwords of 12+ characters are recommended. The user can be required to change it on first login.",
            )
        )
    if not state.get(K.KEY_EMAIL):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Capture an email address",
                detail="Email is optional but useful for password resets and notifications.",
            )
        )
    if not state.get(K.KEY_MUST_CHANGE_PASSWORD):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Force password change recommended",
                detail="Initial passwords are typically shared out-of-band. Forcing a change on first login limits exposure.",
            )
        )
    return msgs


def _roles_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    if not (state.get(K.KEY_ROLE_IDS) or []):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="No roles assigned",
                detail="Without a role this user will not have any application permissions. Roles can be assigned later, but most workflows require at least one.",
            )
        )
    if not state.get(K.KEY_GRANT_CURRENT_COMPANY):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="No company access granted",
                detail="The user will not be able to log in to this company until a company access record is created.",
            )
        )
    return msgs


def _confirm_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Audit-logged provisioning",
            detail="User creation, role assignment, and company access grants are all recorded in the audit log.",
        )
    ]


def build_user_provisioning_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="user_provisioning")
    advisor.register("identity", _identity_rules)
    advisor.register("roles_access", _roles_rules)
    advisor.register("confirm", _confirm_rules)
    return advisor
