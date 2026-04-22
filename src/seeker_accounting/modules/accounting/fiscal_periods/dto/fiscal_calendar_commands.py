from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class CreateFiscalYearCommand:
    year_code: str
    year_name: str
    start_date: date
    end_date: date
    status_code: str = "DRAFT"
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class GenerateFiscalPeriodsCommand:
    periods_per_year: int = 12
    include_adjustment_period: bool = False
    opening_status_code: str = "OPEN"


@dataclass(frozen=True, slots=True)
class ChangePeriodStatusCommand:
    status_code: str
