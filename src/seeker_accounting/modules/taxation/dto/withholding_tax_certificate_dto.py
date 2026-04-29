"""DTOs and command objects for the withholding-tax certificate register.

Phase 5 / Slice T13 of the taxation blueprint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class WithholdingTaxCertificateDTO:
    id: int
    company_id: int
    fiscal_period_id: int | None
    direction: str
    counterparty_kind: str
    counterparty_id: int | None
    counterparty_name: str
    counterparty_niu: str | None
    tax_code_id: int
    certificate_number: str
    certificate_date: date
    source_document_type: str | None
    source_document_id: int | None
    taxable_base: Decimal
    tax_amount: Decimal
    evidence_attachment_path: str | None
    status_code: str
    notes: str | None
    recorded_by_user_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecordWithholdingTaxCertificateCommand:
    direction: str
    counterparty_kind: str
    counterparty_name: str
    tax_code_id: int
    certificate_number: str
    certificate_date: date
    taxable_base: Decimal
    tax_amount: Decimal
    counterparty_id: int | None = None
    counterparty_niu: str | None = None
    fiscal_period_id: int | None = None
    source_document_type: str | None = None
    source_document_id: int | None = None
    evidence_attachment_path: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateWithholdingTaxCertificateCommand:
    certificate_id: int
    counterparty_kind: str
    counterparty_name: str
    tax_code_id: int
    certificate_number: str
    certificate_date: date
    taxable_base: Decimal
    tax_amount: Decimal
    counterparty_id: int | None = None
    counterparty_niu: str | None = None
    fiscal_period_id: int | None = None
    source_document_type: str | None = None
    source_document_id: int | None = None
    evidence_attachment_path: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class VoidWithholdingTaxCertificateCommand:
    certificate_id: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LinkWithholdingCertificateToJournalEntryCommand:
    """Attach an existing certificate to a posted journal entry.

    Used to back-fill the link between an outbound certificate (issued
    to a supplier when withholding was deducted at payment time) and
    the supplier-payment journal entry that recorded the deduction.
    Setting ``journal_entry_id`` to ``None`` clears the link.
    """

    certificate_id: int
    journal_entry_id: int | None


@dataclass(frozen=True, slots=True)
class WithholdingTaxRegisterTotalsDTO:
    """Aggregate totals for a (direction, period) slice of the register.

    Used by the compliance UI to surface "WHT receivable from authority"
    (inbound) and "WHT payable to authority" (outbound) at a glance.
    """

    direction: str
    period_start: date
    period_end: date
    certificate_count: int
    total_taxable_base: Decimal
    total_tax_amount: Decimal
