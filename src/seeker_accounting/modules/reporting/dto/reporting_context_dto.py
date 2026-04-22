from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReportingContextDTO:
    """Assembled reporting context for a given company and fiscal state."""

    company_id: int | None
    company_name: str
    base_currency_code: str | None
    fiscal_period_code: str | None
    fiscal_period_status: str | None
    fiscal_period_label: str | None
    report_basis: str
