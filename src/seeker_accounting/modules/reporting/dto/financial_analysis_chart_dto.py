from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from seeker_accounting.modules.reporting.dto.comparative_analysis_dto import ComparativeAnalysisDTO


@dataclass(frozen=True, slots=True)
class FinancialAnalysisFilterDTO:
    company_id: int
    date_from: date | None
    date_to: date | None


@dataclass(frozen=True, slots=True)
class FinancialChartPointDTO:
    label: str
    value: Decimal
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class FinancialChartSeriesDTO:
    key: str
    label: str
    color_name: str
    points: tuple[FinancialChartPointDTO, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class FinancialChartTableRowDTO:
    key: str
    label: str
    current_value: Decimal | None
    prior_value: Decimal | None = None
    variance_value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class FinancialAnalysisViewDTO:
    view_key: str
    title: str
    subtitle: str
    chart_type: str
    series: tuple[FinancialChartSeriesDTO, ...] = field(default_factory=tuple)
    table_rows: tuple[FinancialChartTableRowDTO, ...] = field(default_factory=tuple)
    table_headers: tuple[str, ...] = ("Value",)
    comparative: ComparativeAnalysisDTO | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    empty_state_message: str | None = None


@dataclass(frozen=True, slots=True)
class FinancialChartDetailRowDTO:
    account_id: int | None
    account_code: str
    account_name: str
    amount: Decimal
    note: str | None = None


@dataclass(frozen=True, slots=True)
class FinancialChartDetailDTO:
    company_id: int
    detail_key: str
    title: str
    subtitle: str
    date_from: date | None
    date_to: date | None
    total_amount: Decimal
    rows: tuple[FinancialChartDetailRowDTO, ...] = field(default_factory=tuple)
    warning_message: str | None = None


@dataclass(frozen=True, slots=True)
class FinancialAnalysisChartReportDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    views: tuple[FinancialAnalysisViewDTO, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
