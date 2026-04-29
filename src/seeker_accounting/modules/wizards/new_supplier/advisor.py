"""Advisor for the New Supplier Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.new_supplier import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _identity_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    code = str(state.get(K.KEY_SUPPLIER_CODE) or "")
    msgs: list[AdvisorMessage] = []
    if code and not any(c.isdigit() for c in code):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Sequential codes",
                detail="Most teams include a number in the supplier code (e.g. SUP-001) for sortable lists.",
            )
        )
    return msgs


def _contact_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if not state.get(K.KEY_EMAIL) and not state.get(K.KEY_PHONE):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Add a contact channel",
                detail="At least one of phone or email is recommended for AP queries and remittance advice.",
            )
        ]
    return []


def _financial_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    if not state.get(K.KEY_PAYMENT_TERM_ID):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="No payment term",
                detail="Without a default payment term, due dates on bills won't auto-compute.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Ready to create",
            detail="You can edit any of these later from the Suppliers page.",
        )
    ]


def build_new_supplier_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="new_supplier")
    advisor.register("identity", _identity_rules)
    advisor.register("contact", _contact_rules)
    advisor.register("financial", _financial_rules)
    return advisor
