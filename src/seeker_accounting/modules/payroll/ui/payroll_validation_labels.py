"""Payroll validation check-code label registrations.

Seeds CODE_LABELS with every check_code emitted by
PayrollValidationDashboardService so that UI components can display
human-readable labels and tooltips without embedding raw codes.

Category: ``payroll_validation``

Import this module once at startup (e.g. from payroll module init or
application bootstrap). It is safe to import multiple times — the
registry silently skips duplicate registrations.
"""
from __future__ import annotations

from seeker_accounting.shared.ui.components.code_label_registry import CODE_LABELS

CODE_LABELS.register_many(
    "payroll_validation",
    {
        # ── Setup ─────────────────────────────────────────────────────────
        "NO_PAYROLL_SETTINGS": (
            "No payroll settings",
            "No payroll settings have been configured for this company. "
            "Complete the Payroll Setup wizard before running payroll.",
            "error",
        ),
        "NO_STATUTORY_PACK": (
            "No statutory pack applied",
            "No statutory pack has been applied. Apply a pack in Payroll Operations > Statutory packs.",
            "error",
        ),
        "PACK_UNVERIFIED_ITEMS": (
            "Unverified pack items",
            "The applied statutory pack contains items that have not been verified against current regulations.",
            "warning",
        ),
        "PACK_PROVISIONAL_ITEMS": (
            "Provisional pack items",
            "The applied statutory pack contains provisional items. Review and confirm before posting.",
            "warning",
        ),
        "BENEFITS_IN_KIND_SETUP_ISSUE": (
            "Benefits-in-kind setup issue",
            "A benefits-in-kind component has a configuration issue that prevents correct valuation.",
            "error",
        ),
        # ── Period ────────────────────────────────────────────────────────
        "NO_FISCAL_PERIOD": (
            "No fiscal period",
            "No open fiscal period was found for the selected payroll period. Create or open the period first.",
            "error",
        ),
        "PERIOD_LOCKED": (
            "Period locked",
            "The fiscal period covering this payroll period is locked. Unlock the period to proceed.",
            "error",
        ),
        "PERIOD_NOT_OPEN": (
            "Period not open",
            "The fiscal period covering this payroll period is not open for posting.",
            "error",
        ),
        # ── Accounts ─────────────────────────────────────────────────────
        "NO_PAYROLL_PAYABLE_ACCOUNT": (
            "No payroll payable account",
            "No payroll payable control account has been mapped. Assign one in Payroll account mappings.",
            "error",
        ),
        "INVALID_PAYROLL_PAYABLE_ACCOUNT": (
            "Invalid payroll payable account",
            "The mapped payroll payable account does not exist or cannot be resolved.",
            "error",
        ),
        "INACTIVE_PAYROLL_PAYABLE_ACCOUNT": (
            "Inactive payroll payable account",
            "The mapped payroll payable account is inactive. Reactivate it or map a different account.",
            "error",
        ),
        "NON_POSTABLE_PAYROLL_PAYABLE_ACCOUNT": (
            "Non-postable payroll payable account",
            "The mapped payroll payable account is not postable (it may be a header/group account).",
            "error",
        ),
        "MISSING_EXPENSE_ACCOUNT": (
            "Missing expense account",
            "One or more payroll components are missing a mapped wage expense account.",
            "error",
        ),
        "MISSING_LIABILITY_ACCOUNT": (
            "Missing liability account",
            "One or more payroll components are missing a mapped liability account.",
            "error",
        ),
        "INACTIVE_MAPPED_ACCOUNT": (
            "Inactive mapped account",
            "A payroll component is mapped to an inactive GL account.",
            "error",
        ),
        "NON_POSTABLE_MAPPED_ACCOUNT": (
            "Non-postable mapped account",
            "A payroll component is mapped to a non-postable GL account (header or group).",
            "error",
        ),
        # ── Employees ─────────────────────────────────────────────────────
        "NO_ACTIVE_EMPLOYEES": (
            "No active employees",
            "There are no active employees in this company. Hire employees before running payroll.",
            "error",
        ),
        "NO_COMPENSATION_PROFILE": (
            "No compensation",
            "One or more active employees have no active compensation for this period.",
            "error",
        ),
        "EFFECTIVE_DATE_GAP": (
            "Effective date gap",
            "An employee's compensation has a gap before the payroll period start.",
            "error",
        ),
        "EFFECTIVE_DATE_AMBIGUITY": (
            "Effective date ambiguity",
            "Two or more compensation records overlap for the same employee in this period.",
            "error",
        ),
        "ASSIGNMENT_EFFECTIVE_DATE_AMBIGUITY": (
            "Assignment date ambiguity",
            "Two or more component assignments overlap for the same employee in this period.",
            "error",
        ),
        "NO_COMPONENT_ASSIGNMENTS": (
            "No component assignments",
            "One or more employees have no active component assignments for this period.",
            "warning",
        ),
        "OVERLAPPING_COMPENSATION_PROFILES": (
            "Overlapping compensation",
            "An employee has overlapping compensation records that must be resolved.",
            "error",
        ),
        "OVERLAPPING_COMPONENT_ASSIGNMENTS": (
            "Overlapping component assignments",
            "An employee has overlapping component assignments that must be resolved.",
            "error",
        ),
        "TERMINATED_STILL_ACTIVE": (
            "Terminated employee still active",
            "An employee with a past termination date is still marked active.",
            "warning",
        ),
        # ── Rules ─────────────────────────────────────────────────────────
        "MISSING_RULE_SET": (
            "Missing rule set",
            "No active payroll rule set was found for this company. Add or activate a rule set.",
            "error",
        ),
        "INVALID_OR_MISSING_RULE_BRACKETS": (
            "Invalid or missing rule brackets",
            "The statutory rule set has missing or invalid tax brackets.",
            "error",
        ),
        "MISSING_OVERTIME_RULE_LINK": (
            "Missing overtime rule link",
            "An overtime component has no linked overtime rule definition.",
            "warning",
        ),
        "CNPS_EMPLOYER_RATE_MISMATCH": (
            "CNPS employer rate mismatch",
            "The CNPS employer contribution rate in the rule set does not match the statutory pack.",
            "warning",
        ),
        "FALLBACK_STATUTORY_CONSTANTS_RELIANCE": (
            "Fallback statutory constants",
            "Calculation will rely on fallback statutory constants because live pack values are unavailable.",
            "warning",
        ),
        # ── Payments ──────────────────────────────────────────────────────
        "PAYMENT_INCONSISTENCY": (
            "Payment inconsistency",
            "A posted payroll run has payment records that do not reconcile to the run total.",
            "warning",
        ),
        "REMITTANCE_INCONSISTENCY": (
            "Remittance inconsistency",
            "A statutory remittance does not reconcile to the corresponding posted payroll lines.",
            "warning",
        ),
    },
)

#: Canonical set of check codes registered by this module.
#: Tests and the CodeLabelRegistry introspection use this to confirm coverage.
PAYROLL_VALIDATION_CHECK_CODES: frozenset[str] = frozenset(
    CODE_LABELS.codes("payroll_validation")
)
