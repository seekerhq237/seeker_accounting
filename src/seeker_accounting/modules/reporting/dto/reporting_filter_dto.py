from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class ReportingFilterDTO:
    """Mutable filter state assembled by the reporting filter bar."""

    company_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    posted_only: bool = True
