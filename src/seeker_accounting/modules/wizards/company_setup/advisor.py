"""Advisor rules for the Company Setup Wizard.

The advisor surfaces guidance, suggestions, and warnings tied to specific
steps. Rules are pure functions over (WizardContext, WizardState).
"""
from __future__ import annotations

from seeker_accounting.modules.wizards.company_setup import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _company_info_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = []
    country = state.get(K.KEY_COMPANY_COUNTRY_CODE)
    currency = state.get(K.KEY_COMPANY_CURRENCY_CODE)
    if country and currency:
        if country in {"CM", "CI", "SN", "BJ", "BF", "TG", "ML"} and currency != "XAF" and currency != "XOF":
            messages.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.SUGGESTION,
                    title="Currency may not match country",
                    detail=(
                        f"Country {country} typically uses XAF or XOF. The "
                        f"selected base currency is {currency}. Confirm this "
                        "matches your statutory accounts."
                    ),
                )
            )
    if not state.get(K.KEY_COMPANY_TAX_IDENTIFIER):
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Tax identifier optional",
                detail="You can add the company's tax ID later from Company Settings.",
            )
        )
    return messages


def _fiscal_year_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = []
    start = state.get(K.KEY_FISCAL_YEAR_START)
    end = state.get(K.KEY_FISCAL_YEAR_END)
    if start and end:
        # Soft guidance: fiscal year typically spans 12 months.
        try:
            from datetime import date as _d

            s = _d.fromisoformat(start)
            e = _d.fromisoformat(end)
            months = (e.year - s.year) * 12 + (e.month - s.month) + 1
            if months != 12:
                messages.append(
                    AdvisorMessage(
                        severity=AdvisorSeverity.WARNING,
                        title="Non-standard fiscal year length",
                        detail=(
                            f"This fiscal year spans {months} months. Standard "
                            "fiscal years are 12 months; short or long years "
                            "may complicate comparative reporting."
                        ),
                    )
                )
        except ValueError:
            pass
    return messages


def _chart_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = []
    if not state.get(K.KEY_COA_SEED_REQUESTED, True):
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Chart will be empty",
                detail=(
                    "Skipping the OHADA chart leaves your company without "
                    "accounts. You must add at least one account in each major "
                    "class before posting transactions."
                ),
            )
        )
    else:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="OHADA SYSCOHADA",
                detail=(
                    "Seeds standard classes 1\u20139 with widely-used accounts. "
                    "You can extend or rename them after the wizard finishes."
                ),
            )
        )
    return messages


def _doc_seq_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = []
    chosen = state.get(K.KEY_DOC_SEQ_TYPES_TO_CREATE) or []
    if not chosen:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="No sequences selected",
                detail=(
                    "Without a journal entry sequence, journal posting will "
                    "fall back to manual numbering. Selecting at least JE\u2011 "
                    "is strongly recommended."
                ),
            )
        )
    return messages


def _tax_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = []
    chosen = state.get(K.KEY_TAX_CODES_TO_CREATE) or []
    if not chosen:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Tax codes recommended",
                detail=(
                    "Most VAT-registered companies need at least one VAT code "
                    "before invoicing. You can edit rates and validity windows "
                    "after the wizard."
                ),
            )
        )
    return messages


def _role_mapping_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Map control accounts before posting",
            detail=(
                "Reference Data \u203a Account Role Mappings lets you assign "
                "specific accounts to AR Control, AP Control, VAT Input/Output, "
                "and Retained Earnings."
            ),
        )
    ]


def _review_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = []
    if not state.get(K.KEY_COMPANY_ID):
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.BLOCKER,
                title="Company not yet created",
                detail="Go back and complete the Company step before finishing.",
            )
        )
    return messages


def build_company_setup_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="company_setup")
    advisor.register("company_info", _company_info_rules)
    advisor.register("fiscal_year", _fiscal_year_rules)
    advisor.register("chart_of_accounts", _chart_rules)
    advisor.register("document_sequences", _doc_seq_rules)
    advisor.register("tax_codes", _tax_rules)
    advisor.register("account_role_mappings", _role_mapping_rules)
    advisor.register("review", _review_rules)
    return advisor
