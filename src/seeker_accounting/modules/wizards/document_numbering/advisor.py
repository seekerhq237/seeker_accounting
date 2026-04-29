"""Advisor for the Document Numbering Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.document_numbering import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _pick_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    mode = state.get(K.KEY_MODE)
    if mode == "update":
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Editing a live sequence",
                detail="Lowering 'next number' below the highest already-issued value can cause duplicate document numbers.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="One sequence per document type",
            detail="Each document type can have only one sequence per company.",
        )
    ]


def _configure_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    pad = state.get(K.KEY_PADDING_WIDTH)
    if isinstance(pad, int) and pad < 4:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Short padding",
                detail="Most teams use a width of 4-6 to keep numbers sortable as text.",
            )
        )
    if state.get(K.KEY_RESET_FREQUENCY_CODE) and not state.get(K.KEY_PREFIX):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Add a date prefix",
                detail="When using monthly/yearly reset, a date prefix (e.g. INV-2026-) makes audit trails clearer.",
            )
        )
    return msgs


def _commit_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return []


def build_document_numbering_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="document_numbering")
    advisor.register("pick", _pick_rules)
    advisor.register("configure", _configure_rules)
    advisor.register("commit", _commit_rules)
    return advisor
