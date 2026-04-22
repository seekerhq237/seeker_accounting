from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DrilldownRequestDTO:
    """Request payload for the report drilldown dialog framework."""

    source_report: str
    drill_type: str  # "account_ledger" | "journal_detail" | "report_line"
    reference_id: int | None
    reference_code: str | None
    display_label: str
    date_from: date | None
    date_to: date | None
    company_id: int
