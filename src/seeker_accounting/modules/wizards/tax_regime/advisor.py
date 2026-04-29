"""Advisor for the Tax Regime Wizard."""
from __future__ import annotations

from seeker_accounting.modules.wizards.tax_regime import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)


def _identity_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    if not state.get(K.KEY_NIU):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="NIU is missing",
                detail="The taxpayer NIU is required for tax filings (DSF, VAT). Capture it now or as soon as available.",
            )
        )
    if state.get(K.KEY_TAX_REGIME_CODE) == "LIBERATORY" and state.get(K.KEY_TAXPAYER_SEGMENT_CODE) == "LARGE":
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="Inconsistent regime/segment",
                detail="The liberatory regime is reserved for very small businesses; LARGE segment is unusual here.",
            )
        )
    return msgs


def _vat_cit_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    regime = state.get(K.KEY_TAX_REGIME_CODE)
    if regime == "REAL" and not state.get(K.KEY_IS_VAT_LIABLE):
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Real regime usually implies VAT",
                detail="Real-regime taxpayers are typically VAT liable. Confirm before continuing.",
            )
        )
    if state.get(K.KEY_SME_QUALIFIED_FLAG) and state.get(K.KEY_CIT_RATE_PROFILE_CODE) != "SME":
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="SME flag without SME CIT profile",
                detail="If the company qualifies as an SME, consider applying the SME CIT rate profile (25%).",
            )
        )
    if state.get(K.KEY_CIT_RATE_PROFILE_CODE) == "EXEMPT":
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="CIT exemption requires evidence",
                detail="Keep the underlying convention or decree on file; tax administration may request it on inspection.",
            )
        )
    return msgs


def _dsf_flags_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    msgs: list[AdvisorMessage] = []
    regime = state.get(K.KEY_TAX_REGIME_CODE)
    dsf = state.get(K.KEY_DSF_FORM_CODE)
    expected_dsf = {"REAL": "DSF_REAL", "SIMPLIFIED": "DSF_SIMPLIFIED", "LIBERATORY": "DSF_LIBERATORY"}.get(
        regime or ""
    )
    if expected_dsf and dsf and dsf != expected_dsf and dsf != "NONE":
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="DSF form may not match regime",
                detail=f"Selected regime {regime} typically files {expected_dsf}, not {dsf}.",
            )
        )
    if not dsf:
        msgs.append(
            AdvisorMessage(
                severity=AdvisorSeverity.SUGGESTION,
                title="Pick a DSF form",
                detail="Select the DSF form that will be used at year-end so the platform can prepare it ahead of time.",
            )
        )
    return msgs


def build_tax_regime_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="tax_regime")
    advisor.register("identity", _identity_rules)
    advisor.register("vat_cit", _vat_cit_rules)
    advisor.register("dsf_flags", _dsf_flags_rules)
    return advisor
