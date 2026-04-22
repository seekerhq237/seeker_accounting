from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class FiscalYearListItemDTO:
    id: int
    company_id: int
    year_code: str
    year_name: str
    start_date: date
    end_date: date
    status_code: str
    is_active: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FiscalPeriodListItemDTO:
    id: int
    company_id: int
    fiscal_year_id: int
    period_number: int
    period_code: str
    period_name: str
    start_date: date
    end_date: date
    status_code: str
    is_adjustment_period: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FiscalYearDTO:
    id: int
    company_id: int
    year_code: str
    year_name: str
    start_date: date
    end_date: date
    status_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    periods: tuple["FiscalPeriodDTO", ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class FiscalPeriodDTO:
    id: int
    company_id: int
    fiscal_year_id: int
    fiscal_year_code: str
    period_number: int
    period_code: str
    period_name: str
    start_date: date
    end_date: date
    status_code: str
    is_adjustment_period: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FiscalCalendarDTO:
    fiscal_year: FiscalYearDTO
    periods: tuple[FiscalPeriodDTO, ...]


@dataclass(frozen=True, slots=True)
class PeriodStatusChangeResultDTO:
    fiscal_period_id: int
    period_code: str
    previous_status_code: str
    status_code: str
    actor_user_id: int | None
    updated_at: datetime
