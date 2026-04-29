"""DTOs for tax obligations, returns, return lines, and payments."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


# ───────────────────────── Obligations ─────────────────────────


@dataclass(frozen=True, slots=True)
class TaxObligationDTO:
    id: int
    company_id: int
    tax_type_code: str
    period_start: date
    period_end: date
    due_date: date
    status_code: str
    notes: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CreateTaxObligationCommand:
    tax_type_code: str
    period_start: date
    period_end: date
    due_date: date
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class GenerateMonthlyVATObligationsCommand:
    """Generate monthly VAT obligations for a calendar year."""

    year: int
    due_day_of_next_month: int = 15


@dataclass(frozen=True, slots=True)
class GenerateQuarterlyCITInstallmentsCommand:
    """Generate the four quarterly CIT installment obligations for a year.

    Each quarter is due in the month following its end (Apr/Jul/Oct of
    the same year, Jan of the following year for Q4). The default day
    mirrors Cameroon DGI practice (15th).
    """

    year: int
    due_day_of_next_month: int = 15


@dataclass(frozen=True, slots=True)
class GenerateMonthlyWithholdingObligationsCommand:
    """Generate the 12 monthly withholding-tax obligations for a year.

    Mirrors the VAT cadence: each month's withholding (collected from
    posted supplier-payment WHT certificates) is due by the configured
    day of the following month (Cameroon DGI default: 15th).
    """

    year: int
    due_day_of_next_month: int = 15


@dataclass(frozen=True, slots=True)
class GenerateAnnualPatenteObligationCommand:
    """Generate the single annual Patente (business-license) obligation.

    Period covers the calendar year. Cameroon DGI default: due
    by end of February of the same year.
    """

    year: int
    due_month: int = 2
    due_day: int = 28


@dataclass(frozen=True, slots=True)
class GenerateMonthlyTSRObligationsCommand:
    """Generate the 12 monthly TSR (specific-service tax) obligations.

    Same cadence as VAT (monthly, due by the 15th of the following
    month by default).
    """

    year: int
    due_day_of_next_month: int = 15


@dataclass(frozen=True, slots=True)
class CreateCustomsDutyObligationCommand:
    """Record a single customs-duty obligation for an import declaration.

    Customs duty is per-declaration, not periodic. ``period_start``
    and ``period_end`` are typically both the declaration date.
    ``declaration_reference`` is stored in ``notes`` so the obligation
    can be reconciled against the customs system.
    """

    declaration_date: date
    due_date: date
    declaration_reference: str | None = None
    notes: str | None = None


# ───────────────────────── Returns ─────────────────────────


@dataclass(frozen=True, slots=True)
class TaxReturnLineDTO:
    id: int | None
    box_code: str
    label: str
    amount: Decimal
    sort_order: int


@dataclass(frozen=True, slots=True)
class TaxReturnDTO:
    id: int
    company_id: int
    obligation_id: int
    tax_type_code: str
    period_start: date
    period_end: date
    status_code: str
    total_due_amount: Decimal
    total_paid_amount: Decimal
    filed_at: datetime | None
    otp_reference: str | None
    external_reference: str | None
    notes: str | None
    prepared_by_user_id: int | None
    lines: tuple[TaxReturnLineDTO, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DraftVATReturnCommand:
    """Generate (or regenerate) the draft VAT return for an obligation."""

    obligation_id: int
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class FileAssessedTaxReturnCommand:
    """File a minimal return for a fixed-amount obligation (Slice T27).

    Used for tax types that do not have an aggregation step
    (Patente, TSR, Customs).  The user enters the assessed amount
    directly and the service creates a return already in the FILED
    state — there is no intermediate draft.
    """

    obligation_id: int
    total_due_amount: Decimal
    filing_date: date | None = None  # defaults to today
    otp_reference: str | None = None
    external_reference: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class FileTaxReturnCommand:
    return_id: int
    otp_reference: str | None = None
    external_reference: str | None = None


# ───────────────────────── Payments ─────────────────────────


@dataclass(frozen=True, slots=True)
class TaxPaymentDTO:
    id: int
    company_id: int
    tax_return_id: int | None
    payment_date: date
    amount: Decimal
    payment_method_code: str
    reference: str | None
    notes: str | None
    journal_entry_id: int | None
    recorded_by_user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecordTaxPaymentCommand:
    tax_return_id: int
    payment_date: date
    amount: Decimal
    payment_method_code: str
    reference: str | None = None
    notes: str | None = None
    # T16: Treasury (cash/bank) account credited by the payment.  When
    # provided, the service posts a bank-side JE (Dr 4441 / Cr treasury)
    # against a settled VAT return.  Optional for backward compatibility
    # with non-VAT returns and existing record-only flows.
    treasury_account_id: int | None = None


# ───────────────────────── Settlement (T15) ─────────────────────────


@dataclass(frozen=True, slots=True)
class TaxSettlementLineDTO:
    """One projected debit/credit line on the settlement journal."""

    account_id: int
    account_code: str
    account_name: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: str
    role: str  # "OUTPUT_VAT" | "INPUT_VAT" | "VAT_PAYABLE" | "VAT_CREDIT_CARRYFORWARD"


@dataclass(frozen=True, slots=True)
class TaxSettlementPreviewDTO:
    """Preview of the settlement journal that ``settle_return`` will post."""

    return_id: int
    company_id: int
    period_start: date
    period_end: date
    settlement_date: date
    total_output_vat: Decimal
    total_input_vat_recoverable: Decimal
    net_payable_amount: Decimal  # > 0 when payable, 0 otherwise
    net_credit_carryforward_amount: Decimal  # > 0 when credit c/f, 0 otherwise
    journal_lines: tuple[TaxSettlementLineDTO, ...]
    blocking_issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaxSettlementResultDTO:
    """Result of a posted settlement."""

    return_id: int
    journal_entry_id: int
    settlement_date: date
    total_output_vat: Decimal
    total_input_vat_recoverable: Decimal
    net_payable_amount: Decimal
    net_credit_carryforward_amount: Decimal


@dataclass(frozen=True, slots=True)
class SettleTaxReturnCommand:
    """Post the settlement journal for a filed VAT return."""

    return_id: int
    settlement_date: date | None = None  # defaults to return.period_end
    description: str | None = None
    actor_user_id: int | None = None


# ───────────────────────── Dashboard (T22) ─────────────────────────


@dataclass(frozen=True, slots=True)
class TaxDashboardObligationSummaryDTO:
    """Per-tax-type counts on the dashboard."""

    tax_type_code: str
    open_count: int
    overdue_count: int
    paid_count: int


@dataclass(frozen=True, slots=True)
class TaxDashboardUpcomingObligationDTO:
    obligation_id: int
    tax_type_code: str
    period_start: date
    period_end: date
    due_date: date
    days_until_due: int  # negative when overdue
    status_code: str


@dataclass(frozen=True, slots=True)
class TaxDashboardSnapshotDTO:
    """Consolidated tax-compliance snapshot for a company / fiscal year."""

    company_id: int
    fiscal_year: int
    as_of_date: date
    total_obligations: int
    open_obligations: int
    overdue_obligations: int
    paid_obligations: int
    cancelled_obligations: int
    returns_draft: int
    returns_filed: int
    returns_settled: int
    returns_filed_unsettled_vat: int  # VAT FILED with no settlement JE
    total_payments_ytd: Decimal
    total_due_filed_returns_ytd: Decimal
    wht_inbound_total_ytd: Decimal
    wht_outbound_total_ytd: Decimal
    by_tax_type: tuple[TaxDashboardObligationSummaryDTO, ...]
    upcoming: tuple[TaxDashboardUpcomingObligationDTO, ...]


# ───────────────────────── Audit trail (T23) ─────────────────────────


@dataclass(frozen=True, slots=True)
class TaxAuditFilterDTO:
    company_id: int
    event_type_code: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    actor_user_id: int | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    limit: int = 200
    offset: int = 0


# ───────────────────────── Return PDF (T24) ─────────────────────────


@dataclass(frozen=True, slots=True)
class ExportTaxReturnPDFCommand:
    """Render a tax return to a printable PDF document."""

    return_id: int
    output_path: str


@dataclass(frozen=True, slots=True)
class ExportTaxReturnPDFResultDTO:
    return_id: int
    output_path: str
    rendered_at: datetime
