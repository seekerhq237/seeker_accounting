"""DTOs for the Payroll Authority registry & component-authority map.

Phase 5 / P5.S1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PayrollAuthorityDTO:
    id: int
    company_id: int
    code: str
    name: str
    jurisdiction_code: str | None
    filing_cadence_code: str
    deadline_rule_code: str | None
    deadline_day: int | None
    gl_liability_account_id: int | None
    is_active: bool
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CreatePayrollAuthorityCommand:
    code: str
    name: str
    jurisdiction_code: str | None = None
    filing_cadence_code: str = "monthly"
    deadline_rule_code: str | None = None
    deadline_day: int | None = None
    gl_liability_account_id: int | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdatePayrollAuthorityCommand:
    name: str | None = None
    jurisdiction_code: str | None = None
    filing_cadence_code: str | None = None
    deadline_rule_code: str | None = None
    deadline_day: int | None = None
    gl_liability_account_id: int | None = None
    is_active: bool | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ComponentAuthorityMappingDTO:
    id: int
    company_id: int
    component_id: int
    component_code: str
    component_name: str
    authority_id: int
    authority_code: str
    authority_name: str
    side: str
    line_kind: str
    fraction: Decimal


@dataclass(frozen=True, slots=True)
class CreateComponentAuthorityMappingCommand:
    component_id: int
    authority_id: int
    side: str = "total"
    line_kind: str = "contribution"
    fraction: Decimal = field(default_factory=lambda: Decimal("1.0"))


# ── Remittance engine results ────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RemittanceLineEstimate:
    """A single, computed remittance line for an authority + period.

    ``source_run_line_ids`` carries the audit trail back to the originating
    :class:`PayrollRunLine` rows aggregated into this estimate.  This makes
    every estimate cell (and any statutory-return box derived from it)
    traceable down to the underlying journal lines via
    ``payroll_run.journal_entry_id`` once the runs are posted.  Required
    for P5.S5 statutory return pre-fill auditability.
    """

    component_id: int
    component_code: str
    component_name: str
    side: str
    line_kind: str
    amount: Decimal
    liability_account_id: int | None
    source_run_line_ids: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RemittanceEstimate:
    """Result of the engine for one (authority, period, run scope)."""

    authority_id: int
    authority_code: str
    authority_name: str
    period_start_date: date
    period_end_date: date
    currency_code: str
    payroll_run_ids: tuple[int, ...]
    lines: tuple[RemittanceLineEstimate, ...]
    total_amount: Decimal
    warnings: tuple[str, ...] = field(default_factory=tuple)


# ── Statutory return pre-fill (P5.S5) ────────────────────────────────


@dataclass(frozen=True, slots=True)
class StatutoryReturnBoxDTO:
    """One pre-filled box on a statutory return form.

    A "box" represents a single labelled line on an external return
    document (e.g. CNPS quarterly form line 3, DGI monthly form box A).
    Each box carries its computed amount AND the set of source
    ``PayrollRunLine`` ids that fed into the computation, so an auditor
    can drill from any box back to the underlying journal lines.
    """

    box_code: str
    box_label: str
    side: str
    line_kind: str
    component_id: int
    component_code: str
    component_name: str
    amount: Decimal
    source_run_line_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StatutoryReturnPrefillDTO:
    """Pre-fill payload for a statutory return form."""

    authority_id: int
    authority_code: str
    authority_name: str
    period_start_date: date
    period_end_date: date
    currency_code: str
    payroll_run_ids: tuple[int, ...]
    boxes: tuple[StatutoryReturnBoxDTO, ...]
    total_amount: Decimal
    warnings: tuple[str, ...] = field(default_factory=tuple)
