"""Reference codes used by the taxation domain.

Centralizing these prevents free-text drift in UI dialogs and lets the
service validate inputs consistently.

The codes deliberately mirror Cameroon's DGI taxonomy because that is
the first jurisdiction Seeker targets, but the layout (sets + Final
strings) is generic and additional jurisdictions can extend it later
through a statutory pack mechanism similar to payroll's.
"""

from __future__ import annotations

from typing import Final


# --- Tax regime ----------------------------------------------------------

TAX_REGIME_REAL: Final = "REAL"
TAX_REGIME_SIMPLIFIED: Final = "SIMPLIFIED"
TAX_REGIME_LIBERATORY: Final = "LIBERATORY"

ALL_TAX_REGIME_CODES: Final[frozenset[str]] = frozenset(
    {TAX_REGIME_REAL, TAX_REGIME_SIMPLIFIED, TAX_REGIME_LIBERATORY}
)


# --- Taxpayer segment ----------------------------------------------------

TAXPAYER_SEGMENT_LARGE: Final = "LARGE"
TAXPAYER_SEGMENT_MEDIUM: Final = "MEDIUM"
TAXPAYER_SEGMENT_DIVISIONAL: Final = "DIVISIONAL"
TAXPAYER_SEGMENT_SPECIALIZED: Final = "SPECIALIZED"

ALL_TAXPAYER_SEGMENT_CODES: Final[frozenset[str]] = frozenset(
    {
        TAXPAYER_SEGMENT_LARGE,
        TAXPAYER_SEGMENT_MEDIUM,
        TAXPAYER_SEGMENT_DIVISIONAL,
        TAXPAYER_SEGMENT_SPECIALIZED,
    }
)


# --- Corporate income tax rate profile -----------------------------------

CIT_RATE_PROFILE_STANDARD: Final = "STANDARD"      # 30% + CAC
CIT_RATE_PROFILE_SME: Final = "SME"                # 25% + CAC
CIT_RATE_PROFILE_EXEMPT: Final = "EXEMPT"          # explicit exemption

ALL_CIT_RATE_PROFILE_CODES: Final[frozenset[str]] = frozenset(
    {CIT_RATE_PROFILE_STANDARD, CIT_RATE_PROFILE_SME, CIT_RATE_PROFILE_EXEMPT}
)


# --- Corporate income tax installment profile ---------------------------
#
# How a company's CIT instalments are scheduled. Cameroon DGI's default
# cadence is quarterly (filed by the 15th of the month following each
# quarter end); SMEs may settle on a different cadence depending on
# segment. ``NONE`` is used when CIT obligations are tracked manually or
# the entity is exempt.

CIT_INSTALLMENT_PROFILE_QUARTERLY: Final = "QUARTERLY"
CIT_INSTALLMENT_PROFILE_NONE: Final = "NONE"

ALL_CIT_INSTALLMENT_PROFILE_CODES: Final[frozenset[str]] = frozenset(
    {CIT_INSTALLMENT_PROFILE_QUARTERLY, CIT_INSTALLMENT_PROFILE_NONE}
)


# --- DSF form code -------------------------------------------------------

DSF_FORM_REAL: Final = "DSF_REAL"
DSF_FORM_SIMPLIFIED: Final = "DSF_SIMPLIFIED"
DSF_FORM_LIBERATORY: Final = "DSF_LIBERATORY"
DSF_FORM_NONE: Final = "NONE"

ALL_DSF_FORM_CODES: Final[frozenset[str]] = frozenset(
    {DSF_FORM_REAL, DSF_FORM_SIMPLIFIED, DSF_FORM_LIBERATORY, DSF_FORM_NONE}
)


# --- DSF submission mode -------------------------------------------------

DSF_SUBMISSION_EXCEL: Final = "EXCEL"
DSF_SUBMISSION_API: Final = "API"
DSF_SUBMISSION_MANUAL: Final = "MANUAL"

ALL_DSF_SUBMISSION_MODES: Final[frozenset[str]] = frozenset(
    {DSF_SUBMISSION_EXCEL, DSF_SUBMISSION_API, DSF_SUBMISSION_MANUAL}
)


# --- Tax type (obligations / returns / payments) -------------------------

TAX_TYPE_VAT: Final = "VAT"
TAX_TYPE_CIT_INSTALLMENT: Final = "CIT_INSTALLMENT"
TAX_TYPE_CIT_BALANCE: Final = "CIT_BALANCE"
TAX_TYPE_PAYROLL_IRPP: Final = "PAYROLL_IRPP"
TAX_TYPE_PAYROLL_CNPS: Final = "PAYROLL_CNPS"
TAX_TYPE_EXCISE: Final = "EXCISE"
TAX_TYPE_DSF: Final = "DSF"
TAX_TYPE_WITHHOLDING: Final = "WITHHOLDING"
# Slice T19: annual business-license tax (Cameroon "Patente").
TAX_TYPE_PATENTE: Final = "PATENTE"
# Slice T20: tax on specific services (Cameroon "TSR" - taxe sur la
# rente spécifique / specific service tax: insurance, telecom, gaming).
TAX_TYPE_TSR: Final = "TSR"
# Slice T21: customs duty / import tax obligations (per-declaration,
# not a periodic cadence). Created ad-hoc when an import declaration
# is processed.
TAX_TYPE_CUSTOMS: Final = "CUSTOMS"

ALL_TAX_TYPE_CODES: Final[frozenset[str]] = frozenset(
    {
        TAX_TYPE_VAT,
        TAX_TYPE_CIT_INSTALLMENT,
        TAX_TYPE_CIT_BALANCE,
        TAX_TYPE_PAYROLL_IRPP,
        TAX_TYPE_PAYROLL_CNPS,
        TAX_TYPE_EXCISE,
        TAX_TYPE_DSF,
        TAX_TYPE_WITHHOLDING,
        TAX_TYPE_PATENTE,
        TAX_TYPE_TSR,
        TAX_TYPE_CUSTOMS,
    }
)


# --- Tax obligation status -----------------------------------------------

OBLIGATION_STATUS_OPEN: Final = "OPEN"
OBLIGATION_STATUS_IN_PROGRESS: Final = "IN_PROGRESS"
OBLIGATION_STATUS_FILED: Final = "FILED"
OBLIGATION_STATUS_PAID: Final = "PAID"
OBLIGATION_STATUS_OVERDUE: Final = "OVERDUE"
OBLIGATION_STATUS_CANCELLED: Final = "CANCELLED"

ALL_OBLIGATION_STATUS_CODES: Final[frozenset[str]] = frozenset(
    {
        OBLIGATION_STATUS_OPEN,
        OBLIGATION_STATUS_IN_PROGRESS,
        OBLIGATION_STATUS_FILED,
        OBLIGATION_STATUS_PAID,
        OBLIGATION_STATUS_OVERDUE,
        OBLIGATION_STATUS_CANCELLED,
    }
)


# --- Tax return status ---------------------------------------------------

RETURN_STATUS_DRAFT: Final = "DRAFT"
RETURN_STATUS_REVIEWED: Final = "REVIEWED"
RETURN_STATUS_FILED: Final = "FILED"
RETURN_STATUS_AMENDED: Final = "AMENDED"
RETURN_STATUS_CANCELLED: Final = "CANCELLED"

ALL_RETURN_STATUS_CODES: Final[frozenset[str]] = frozenset(
    {
        RETURN_STATUS_DRAFT,
        RETURN_STATUS_REVIEWED,
        RETURN_STATUS_FILED,
        RETURN_STATUS_AMENDED,
        RETURN_STATUS_CANCELLED,
    }
)


# --- Tax return line / box codes (Cameroon VAT minimal set) --------------

# These are the canonical box identifiers we read into a draft monthly
# VAT return. Additional jurisdictions / CIT / payroll returns will
# extend this list — keep frozenset checks permissive at the service
# level so unknown box codes are stored as-is when imported from
# a statutory pack.
VAT_BOX_OUTPUT_TAX: Final = "VAT_OUTPUT"          # VAT collected on sales
VAT_BOX_INPUT_TAX_DEDUCTIBLE: Final = "VAT_INPUT_DEDUCTIBLE"  # recoverable VAT on purchases
VAT_BOX_INPUT_TAX_NON_DEDUCTIBLE: Final = "VAT_INPUT_NON_DEDUCTIBLE"  # non-recoverable VAT
VAT_BOX_NET_VAT_DUE: Final = "VAT_NET_DUE"        # output - input deductible
VAT_BOX_TAXABLE_SALES: Final = "TAXABLE_SALES"
VAT_BOX_TAXABLE_PURCHASES: Final = "TAXABLE_PURCHASES"


# --- Tax payment method --------------------------------------------------

TAX_PAYMENT_METHOD_BANK_TRANSFER: Final = "BANK_TRANSFER"
TAX_PAYMENT_METHOD_OTP: Final = "OTP"
TAX_PAYMENT_METHOD_CHEQUE: Final = "CHEQUE"
TAX_PAYMENT_METHOD_CASH: Final = "CASH"
TAX_PAYMENT_METHOD_OTHER: Final = "OTHER"

ALL_TAX_PAYMENT_METHODS: Final[frozenset[str]] = frozenset(
    {
        TAX_PAYMENT_METHOD_BANK_TRANSFER,
        TAX_PAYMENT_METHOD_OTP,
        TAX_PAYMENT_METHOD_CHEQUE,
        TAX_PAYMENT_METHOD_CASH,
        TAX_PAYMENT_METHOD_OTHER,
    }
)


# --- Withholding tax certificate (Slice T13) -----------------------------

WHT_DIRECTION_INBOUND: Final = "INBOUND"
WHT_DIRECTION_OUTBOUND: Final = "OUTBOUND"

ALL_WHT_DIRECTION_CODES: Final[frozenset[str]] = frozenset(
    {WHT_DIRECTION_INBOUND, WHT_DIRECTION_OUTBOUND}
)

WHT_COUNTERPARTY_CUSTOMER: Final = "CUSTOMER"
WHT_COUNTERPARTY_SUPPLIER: Final = "SUPPLIER"
WHT_COUNTERPARTY_OTHER: Final = "OTHER"

ALL_WHT_COUNTERPARTY_KINDS: Final[frozenset[str]] = frozenset(
    {WHT_COUNTERPARTY_CUSTOMER, WHT_COUNTERPARTY_SUPPLIER, WHT_COUNTERPARTY_OTHER}
)

WHT_STATUS_ISSUED: Final = "ISSUED"      # outbound: we issued it
WHT_STATUS_RECEIVED: Final = "RECEIVED"  # inbound: customer issued it to us
WHT_STATUS_VOIDED: Final = "VOIDED"

ALL_WHT_STATUS_CODES: Final[frozenset[str]] = frozenset(
    {WHT_STATUS_ISSUED, WHT_STATUS_RECEIVED, WHT_STATUS_VOIDED}
)


# --- VAT settlement (Slice T15) ------------------------------------------

# Cameroon-default OHADA settlement accounts.  These are looked up by
# code on the company's chart of accounts; falling back to a static
# code keeps the settlement service decoupled from chart-role wiring,
# which only some companies populate.  When the board adds a
# dedicated chart-role mapping for VAT settlement (separate slice),
# the service can be re-pointed at that role without breaking
# behaviour for companies that rely on the default codes.
SETTLEMENT_VAT_PAYABLE_ACCOUNT_CODE: Final = "4441"
SETTLEMENT_VAT_CREDIT_CARRYFORWARD_ACCOUNT_CODE: Final = "4449"


# --- Assessed-amount returns and payment posting (Slice T27) ------------
#
# Patente / TSR / Customs obligations are not aggregated from posted
# accounting facts the way VAT is.  The user enters the assessed
# amount on the obligation directly, the service files a minimal
# return that captures that amount, and the bank-side payment JE is
# posted against a tax-type-specific debit account when the payment
# clears.  The default OHADA codes below match the Cameroon SYSCOHADA
# v1 chart bundled with Seeker; companies that customise their chart
# can later override these via a chart-role mapping (deferred).

# Patente (annual business-licence tax) — direct expense on payment.
PAYMENT_PATENTE_EXPENSE_ACCOUNT_CODE: Final = "6412"
# TSR (tax on specific services) — accumulates as a State liability
# during supplier billing and is cleared on remittance.
PAYMENT_TSR_PAYABLE_ACCOUNT_CODE: Final = "4478"
# Customs duty — direct expense on payment when not capitalised into
# inventory cost.  Capitalisation flows are out of scope for T27.
PAYMENT_CUSTOMS_EXPENSE_ACCOUNT_CODE: Final = "6468"

# Tax types that follow the assessed-amount workflow (no aggregation).
ALL_ASSESSED_RETURN_TAX_TYPES: Final[frozenset[str]] = frozenset(
    {TAX_TYPE_PATENTE, TAX_TYPE_TSR, TAX_TYPE_CUSTOMS}
)

# Debit-side account code dispatched by tax type when posting a bank-side
# payment journal for an assessed-amount return.  Credit side is always
# the treasury account chosen on the payment dialog.
ASSESSED_PAYMENT_DEBIT_ACCOUNT_CODE_BY_TAX_TYPE: Final[dict[str, str]] = {
    TAX_TYPE_PATENTE: PAYMENT_PATENTE_EXPENSE_ACCOUNT_CODE,
    TAX_TYPE_TSR: PAYMENT_TSR_PAYABLE_ACCOUNT_CODE,
    TAX_TYPE_CUSTOMS: PAYMENT_CUSTOMS_EXPENSE_ACCOUNT_CODE,
}

