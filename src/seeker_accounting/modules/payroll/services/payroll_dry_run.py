"""Dry-run preview helpers for the Payroll Run cockpit (Phase 3 / P3.S3).

Provides a pure descriptive estimate consumed by the cockpit's
"Confirm calculation" dialog. The estimate is intentionally cheap — it
never runs the full calculation engine. It surfaces:

* the run's period + currency
* the count of active employees the calculation will touch
* anchor totals from a *prior run* in the same currency (if any)
* the count of outstanding (draft / approved) variable-input batches
  for the same period that the calculation will pick up

This is consumed by :class:`PayrollRunService.estimate_calculation`
or directly by the UI when only DTO-level data is needed; the UI
tolerates a missing service method gracefully.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PayrollDryRunEstimate:
    """Lightweight pre-flight summary for the calculate confirmation."""

    run_reference: str
    period_year: int
    period_month: int
    currency_code: str

    # Number of employees the calculation will attempt to process.
    employee_count: int

    # Anchor totals from the previous successful run on the same
    # company + currency. ``None`` when there is no prior run.
    prior_total_gross: Decimal | None = None
    prior_total_net: Decimal | None = None
    prior_run_reference: str | None = None
    prior_period_label: str | None = None

    # Counts of variable-input batches that the calculation will
    # consume.
    approved_input_batches: int = 0
    draft_input_batches: int = 0

    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_prior(self) -> bool:
        return self.prior_total_gross is not None
