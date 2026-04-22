"""ValidationCheckDetailDialog — full detail and remediation steps for a validation check."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.payroll.dto.payroll_validation_dashboard_dto import ValidationCheckDTO

# ── Remediation guidance keyed by check_code ─────────────────────────────────

_REMEDIATION: dict[str, str] = {
    "NO_PAYROLL_SETTINGS": (
        "1. Open <b>Payroll Operations</b> and click <b>Company Settings</b> "
        "(or go to <b>Payroll Setup → Company Payroll Settings</b>).<br>"
        "2. Set the <b>Default Pay Frequency</b> and <b>Default Payroll Currency</b> "
        "(both are required).<br>"
        "3. Optionally configure the <b>CNPS Regime</b>, <b>Accident Risk Class</b>, "
        "<b>Overtime Policy Mode</b>, and <b>Benefits-in-Kind Mode</b>.<br>"
        "4. Save and run the assessment again."
    ),
    "NO_STATUTORY_PACK": (
        "1. Go to <b>Payroll Operations → Statutory Packs</b> tab.<br>"
        "2. Select the statutory pack for your jurisdiction "
        "(e.g. <b>CMR_2024_V1</b> for Cameroon).<br>"
        "3. Click <b>Apply Selected Pack</b>.<br>"
        "4. This seeds all required statutory components and rule sets in one step."
    ),
    "PACK_UNVERIFIED_ITEMS": (
        "1. Go to <b>Payroll Operations → Statutory Packs</b> and review the "
        "pack's verification summary.<br>"
        "2. Each unverified item uses a placeholder value. Cross-check every one "
        "against official CNPS/DGI publications for the current fiscal year.<br>"
        "3. Correct incorrect values in <b>Payroll Setup → Components</b> or "
        "<b>Payroll Setup → Rule Sets</b> as appropriate.<br>"
        "4. Do not run production payroll until all unverified items are resolved."
    ),
    "PACK_PROVISIONAL_ITEMS": (
        "1. Confirm the provisional values (CRTV brackets, TDL amounts, etc.) against "
        "the current Finance Law or DGI/CNPS circulars for this fiscal year.<br>"
        "2. If the values match official sources, no action is required.<br>"
        "3. If they differ, update the relevant rule set brackets in "
        "<b>Payroll Setup → Rule Sets</b>."
    ),
    "NO_FISCAL_PERIOD": (
        "1. Go to <b>Accounting → Fiscal Periods</b>.<br>"
        "2. Create a fiscal period covering the selected payroll month "
        "(e.g. 1 March 2026 – 31 March 2026).<br>"
        "3. Set its status to <b>OPEN</b>.<br>"
        "4. Return here and run the assessment again."
    ),
    "PERIOD_LOCKED": (
        "1. Go to <b>Accounting → Fiscal Periods</b>.<br>"
        "2. Find the period covering your payroll date.<br>"
        "3. Change its status from <b>LOCKED</b> to <b>OPEN</b>.<br>"
        "<b>Note:</b> If you cannot unlock the period, consult your accounting "
        "administrator — a lock may indicate the books are officially closed for "
        "that period."
    ),
    "PERIOD_NOT_OPEN": (
        "1. Go to <b>Accounting → Fiscal Periods</b>.<br>"
        "2. Find the period covering your selected payroll month.<br>"
        "3. Change its status to <b>OPEN</b>.<br>"
        "4. A period must be in OPEN status for payroll journal entries to be posted."
    ),
    "NO_PAYROLL_PAYABLE_ACCOUNT": (
        "1. Go to <b>Accounting Setup → Account Roles</b>.<br>"
        "2. Add a mapping for role code <b>payroll_payable</b>.<br>"
        "3. Point it to the correct liability account in your chart of accounts "
        "(typically a class 4 account, e.g. account 421 — Dettes envers le personnel).<br>"
        "4. Ensure the account is active and has <b>Allow posting</b> enabled."
    ),
    "INVALID_PAYROLL_PAYABLE_ACCOUNT": (
        "1. Go to <b>Accounting Setup → Account Roles</b>.<br>"
        "2. Remove the existing <b>payroll_payable</b> role mapping — the account it "
        "referenced no longer exists.<br>"
        "3. Create a new mapping pointing to a valid, active account in your chart "
        "of accounts."
    ),
    "INACTIVE_PAYROLL_PAYABLE_ACCOUNT": (
        "1. <b>Option A</b> — Go to <b>Accounting → Chart of Accounts</b>, find the "
        "payroll payable account, and activate it.<br>"
        "2. <b>Option B</b> — Go to <b>Accounting Setup → Account Roles</b> and remap "
        "the <b>payroll_payable</b> role to a different active account."
    ),
    "NON_POSTABLE_PAYROLL_PAYABLE_ACCOUNT": (
        "1. <b>Option A</b> — Go to <b>Accounting → Chart of Accounts</b>, find the "
        "payroll payable account, and enable <b>Allow posting</b> on it.<br>"
        "2. <b>Option B</b> — Go to <b>Accounting Setup → Account Roles</b> and remap "
        "the <b>payroll_payable</b> role to a postable leaf account."
    ),
    "NO_ACTIVE_EMPLOYEES": (
        "1. Go to <b>Payroll Setup → Employees</b>.<br>"
        "2. Add the employees who should be included in payroll.<br>"
        "3. Ensure each employee's status is <b>Active</b>."
    ),
    "NO_COMPENSATION_PROFILE": (
        "1. Go to <b>Payroll Setup → Employees</b> and open the employee shown in "
        "the <b>Entity</b> column above.<br>"
        "2. Open the <b>Compensation Profiles</b> section and add a profile.<br>"
        "3. Set <b>Effective From</b> to on or before the first day of the payroll "
        "period.<br>"
        "4. Enter the employee's gross salary or relevant rate."
    ),
    "EFFECTIVE_DATE_GAP": (
        "1. Go to <b>Payroll Setup → Employees → [Employee] → Compensation "
        "Profiles</b>.<br>"
        "2. The employee has profiles, but none cover the selected payroll period.<br>"
        "3. Either add a new profile with <b>Effective From</b> on or before the 1st "
        "of the payroll month, or extend the <b>Effective To</b> date of an existing "
        "profile so it covers the full period."
    ),
    "EFFECTIVE_DATE_AMBIGUITY": (
        "1. Go to <b>Payroll Setup → Employees → [Employee] → Compensation "
        "Profiles</b>.<br>"
        "2. Multiple profiles are active for the same period — only one is permitted "
        "per period.<br>"
        "3. Set an <b>Effective To</b> end date on the older profile so it closes "
        "before the newer one begins.<br>"
        "4. Verify that only one profile is active for the payroll month."
    ),
    "NO_COMPONENT_ASSIGNMENTS": (
        "1. Go to <b>Payroll Setup → Employees → [Employee] → Component "
        "Assignments</b>.<br>"
        "2. Assign the payroll components this employee should receive "
        "(e.g. BASIC_SALARY, EMPLOYEE_CNPS, IRPP).<br>"
        "3. Set <b>Effective From</b> to on or before the 1st of the payroll month.<br>"
        "<b>Note:</b> This is a warning — payroll can still run, but the employee "
        "will have no earnings or deductions."
    ),
    "ASSIGNMENT_EFFECTIVE_DATE_AMBIGUITY": (
        "1. Go to <b>Payroll Setup → Employees → [Employee] → Component "
        "Assignments</b>.<br>"
        "2. The employee has multiple active assignments for the same component in "
        "the same period. Only one is allowed at a time.<br>"
        "3. Set an <b>Effective To</b> end date on the older assignment so it closes "
        "before the newer one starts.<br>"
        "4. Verify that only one assignment per component is active per period."
    ),
    "TERMINATED_STILL_ACTIVE": (
        "1. Go to <b>Payroll Setup → Employees</b> and open the employee shown.<br>"
        "2. If the employee should no longer appear in payroll: set their status to "
        "<b>Inactive</b> or <b>Terminated</b>.<br>"
        "3. If the termination date was recorded in error: clear or correct it in "
        "the employee record."
    ),
    "OVERLAPPING_COMPENSATION_PROFILES": (
        "1. Go to <b>Payroll Setup → Employees → [Employee] → Compensation "
        "Profiles</b>.<br>"
        "2. Review all profile date ranges — two or more profiles overlap.<br>"
        "3. Set an <b>Effective To</b> end date on the profile that should have ended "
        "first so that the date ranges no longer overlap.<br>"
        "4. Profiles must be sequential and non-overlapping."
    ),
    "OVERLAPPING_COMPONENT_ASSIGNMENTS": (
        "1. Go to <b>Payroll Setup → Employees → [Employee] → Component "
        "Assignments</b>.<br>"
        "2. The entity column shows which employee is affected.<br>"
        "3. Find the component assignments with overlapping date ranges for the same "
        "component.<br>"
        "4. Set an <b>Effective To</b> end date on the older assignment so it ends "
        "before the newer one begins."
    ),
    "MISSING_EXPENSE_ACCOUNT": (
        "1. Go to <b>Payroll Setup → Components</b> and open the component shown "
        "in the <b>Entity</b> column above.<br>"
        "2. Map an <b>Expense Account</b> from your chart of accounts.<br>"
        "3. For earnings: typically a class 6 wages/salaries expense account "
        "(e.g. 661100 — Salaires bruts).<br>"
        "4. For employer contributions: use the corresponding employer charge "
        "expense account (e.g. 663 — Charges sociales)."
    ),
    "MISSING_LIABILITY_ACCOUNT": (
        "1. Go to <b>Payroll Setup → Components</b> and open the component shown "
        "in the <b>Entity</b> column above.<br>"
        "2. Map a <b>Liability Account</b> from your chart of accounts.<br>"
        "3. For deductions and statutory taxes: typically a class 4 account "
        "(e.g. 431 — CNPS à payer, 4441 — État IRPP à payer).<br>"
        "4. Ensure the account is active and has <b>Allow posting</b> enabled."
    ),
    "INACTIVE_MAPPED_ACCOUNT": (
        "1. <b>Option A</b> — Go to <b>Accounting → Chart of Accounts</b>, find the "
        "inactive account shown in the message above, and activate it.<br>"
        "2. <b>Option B</b> — Go to <b>Payroll Setup → Components</b>, open the "
        "component shown in the Entity column, and remap it to a different active "
        "account."
    ),
    "NON_POSTABLE_MAPPED_ACCOUNT": (
        "1. The mapped account is a header or summary account — only leaf accounts "
        "can receive journal entries.<br>"
        "2. <b>Option A</b> — Go to <b>Accounting → Chart of Accounts</b> and enable "
        "<b>Allow posting</b> on the account (if it truly is a detail account).<br>"
        "3. <b>Option B</b> — Go to <b>Payroll Setup → Components</b> and remap the "
        "component to the correct postable leaf account."
    ),
    "BENEFITS_IN_KIND_SETUP_ISSUE": (
        "1. Go to <b>Payroll Setup → Components</b> and open the BIK component "
        "shown.<br>"
        "2. Ensure the component type is set to <b>Earning</b> — not deduction "
        "or other.<br>"
        "3. Ensure the <b>Taxable</b> flag is checked — benefits in kind must be "
        "included in the IRPP taxable base per DGI regulations.<br>"
        "4. Go to <b>Company Payroll Settings</b> and ensure a "
        "<b>Benefits-in-Kind Mode</b> is selected (DGI Table or Company Policy)."
    ),
    "MISSING_RULE_SET": (
        "1. <b>Fastest fix:</b> go to <b>Payroll Operations → Statutory Packs</b> "
        "and click <b>Apply Selected Pack</b> — this seeds all required rule sets "
        "in one step.<br>"
        "2. Alternatively, go to <b>Payroll Setup → Rule Sets</b> and manually "
        "create the rule set shown in the <b>Entity</b> column with the correct "
        "bracket configuration.<br>"
        "3. Ensure the rule set's <b>Effective From</b> date is on or before the "
        "first day of the current payroll period."
    ),
    "INVALID_OR_MISSING_RULE_BRACKETS": (
        "1. Go to <b>Payroll Setup → Rule Sets</b> and open the rule set shown in "
        "the <b>Entity</b> column.<br>"
        "2. Review the bracket configuration:<br>"
        "&nbsp;&nbsp;• Add at least one bracket row if none exist.<br>"
        "&nbsp;&nbsp;• Ensure each bracket has a rate percentage or fixed amount.<br>"
        "&nbsp;&nbsp;• Ensure upper bounds are strictly greater than lower bounds.<br>"
        "&nbsp;&nbsp;• Remove any negative values.<br>"
        "3. Alternatively, re-apply the statutory pack from <b>Payroll Operations → "
        "Statutory Packs</b> to reseed the rule set with correct official values."
    ),
    "MISSING_OVERTIME_RULE_LINK": (
        "1. An approved input batch has overtime quantity entries, but no "
        "<b>OVERTIME_STANDARD</b> rule set is configured for this period.<br>"
        "2. Go to <b>Payroll Setup → Rule Sets</b> and create an "
        "<b>OVERTIME_STANDARD</b> rule set with multiplier bracket rows per the "
        "Cameroon Labour Code overtime scale.<br>"
        "3. Ensure its <b>Effective From</b> date covers the current payroll period.<br>"
        "4. Alternatively, apply the statutory pack — it may include a default "
        "overtime rule configuration."
    ),
    "CNPS_EMPLOYER_RATE_MISMATCH": (
        "1. The CNPS_EMPLOYER_MAIN rule set's first bracket rate exceeds the correct "
        "value.<br>"
        "2. The statutory CNPS PVID rate is split equally: "
        "<b>4.20% employer + 4.20% employee = 8.40% total</b>.<br>"
        "3. Go to <b>Payroll Setup → Rule Sets → CNPS_EMPLOYER_MAIN</b> and set "
        "the first bracket rate to exactly <b>4.20%</b>.<br>"
        "4. Alternatively, re-apply the statutory pack from <b>Payroll Operations → "
        "Statutory Packs</b> to reseed the correct rate automatically."
    ),
    "FALLBACK_STATUTORY_CONSTANTS_RELIANCE": (
        "1. This is a summary warning: one or more required rule sets are absent, "
        "so the engine will use hard-coded fallback constants instead of your "
        "configured statutory values.<br>"
        "2. <b>Fastest fix:</b> go to <b>Payroll Operations → Statutory Packs</b> "
        "and click <b>Apply Selected Pack</b> to seed all required rule sets at once.<br>"
        "3. Review the individual <b>Missing Rule Set</b> warnings in this assessment "
        "for the specific rule sets that need to be created."
    ),
    "PAYMENT_INCONSISTENCY": (
        "1. Go to <b>Payroll → Payroll Runs</b> and open the run referenced in the "
        "message above.<br>"
        "2. Find the employee's payment records.<br>"
        "3. If <b>overpaid</b>: remove or correct any duplicate or excess payment "
        "entries so that the total does not exceed net payable.<br>"
        "4. If <b>status mismatch</b>: review the payment total and update the "
        "payment status to reflect the correct state (unpaid / partial / paid).<br>"
        "5. Contact your payroll administrator if a manual journal correction is "
        "also required."
    ),
    "REMITTANCE_INCONSISTENCY": (
        "1. Go to <b>Payroll → Remittances</b> and open the batch referenced in "
        "the message above.<br>"
        "2. Review all payment records attached to the batch.<br>"
        "3. If <b>overpaid</b>: identify and remove duplicate payment entries so "
        "that the total does not exceed the amount due.<br>"
        "4. If <b>status mismatch</b>: the batch is marked paid but the payment "
        "total is below the due amount — add missing payment records or correct "
        "the status if it was updated in error."
    ),
}

_SEVERITY_META: dict[str, tuple[str, str]] = {
    "error":   ("ERROR",   "#dc3545"),
    "warning": ("WARNING", "#fd7e14"),
    "info":    ("INFO",    "#0d6efd"),
}

_CATEGORY_LABELS: dict[str, str] = {
    "setup":       "Setup",
    "employees":   "Employees",
    "accounts":    "Accounts",
    "period":      "Fiscal Period",
    "rules":       "Payroll Rules",
    "components":  "Components",
    "payments":    "Payments",
    "remittances": "Remittances",
}


class ValidationCheckDetailDialog(QDialog):
    """Full-detail view for a single payroll validation check with remediation steps."""

    def __init__(self, check: ValidationCheckDTO, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Validation Check — Details")
        self.setModal(True)
        self.setMinimumSize(560, 480)
        self.resize(680, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scrollable body ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 16)
        body_layout.setSpacing(16)

        # ── Severity badge + title ────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        sev_label, sev_color = _SEVERITY_META.get(check.severity, ("INFO", "#0d6efd"))
        badge = QLabel(sev_label)
        badge.setFixedSize(70, 22)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {sev_color}; color: white; border-radius: 4px;"
            " font-size: 11px; font-weight: 600;"
        )
        header_row.addWidget(badge)

        title_lbl = QLabel(check.title)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        title_lbl.setWordWrap(True)
        header_row.addWidget(title_lbl, 1)
        body_layout.addLayout(header_row)

        # ── Meta card: category / entity / check code ─────────────────────────
        meta_card = QFrame()
        meta_card.setObjectName("PageCard")
        meta_layout = QVBoxLayout(meta_card)
        meta_layout.setContentsMargins(14, 10, 14, 10)
        meta_layout.setSpacing(5)

        cat_display = _CATEGORY_LABELS.get(check.category, check.category.title())
        meta_layout.addWidget(_meta_row("Category", cat_display))

        if check.entity_label:
            etype = f" <span style='color:#888; font-size:11px;'>({check.entity_type})</span>" \
                if check.entity_type else ""
            meta_layout.addWidget(_meta_row("Entity", check.entity_label + etype))

        if check.check_code:
            meta_layout.addWidget(
                _meta_row("Check Code", f"<code style='font-size:11px;'>{check.check_code}</code>")
            )

        body_layout.addWidget(meta_card)

        # ── Full message ──────────────────────────────────────────────────────
        msg_hdr = QLabel("Details")
        msg_hdr.setObjectName("CardTitle")
        body_layout.addWidget(msg_hdr)

        msg_lbl = QLabel(check.message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setTextFormat(Qt.TextFormat.RichText)
        msg_lbl.setStyleSheet("font-size: 13px; line-height: 1.5; padding: 2px 0;")
        msg_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        body_layout.addWidget(msg_lbl)

        # ── Remediation steps ─────────────────────────────────────────────────
        remediation = _REMEDIATION.get(check.check_code or "")
        if remediation:
            fix_hdr = QLabel("How to fix this")
            fix_hdr.setObjectName("CardTitle")
            body_layout.addWidget(fix_hdr)

            fix_card = QFrame()
            fix_card.setObjectName("PageCard")
            fix_layout = QVBoxLayout(fix_card)
            fix_layout.setContentsMargins(14, 12, 14, 12)

            fix_lbl = QLabel(remediation)
            fix_lbl.setWordWrap(True)
            fix_lbl.setTextFormat(Qt.TextFormat.RichText)
            fix_lbl.setOpenExternalLinks(False)
            fix_lbl.setStyleSheet("font-size: 13px; line-height: 1.65;")
            fix_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            fix_layout.addWidget(fix_lbl)
            body_layout.addWidget(fix_card)
        else:
            no_fix = QLabel(
                "<i style='color:#888;'>No specific remediation guide is available for "
                "this check code. Review the details above and consult your payroll "
                "administrator.</i>"
            )
            no_fix.setWordWrap(True)
            no_fix.setTextFormat(Qt.TextFormat.RichText)
            body_layout.addWidget(no_fix)

        body_layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── Bottom bar with Close button ──────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setStyleSheet("border-top: 1px solid #e0e0e0;")
        btn_bar_layout = QHBoxLayout(btn_bar)
        btn_bar_layout.setContentsMargins(16, 8, 16, 8)
        btn_bar_layout.addStretch()
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        btn_bar_layout.addWidget(close_box)
        root.addWidget(btn_bar)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.validation_check_detail", dialog=True)


def _meta_row(label: str, value: str) -> QLabel:
    lbl = QLabel(f"<b>{label}:</b>&nbsp; {value}")
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setStyleSheet("font-size: 12px;")
    return lbl
