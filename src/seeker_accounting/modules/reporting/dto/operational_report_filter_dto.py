from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True, slots=True)
class OperationalReportFilterDTO:
    company_id: int | None
    date_from: date | None = None
    date_to: date | None = None
    as_of_date: date | None = None
    customer_id: int | None = None
    supplier_id: int | None = None
    payroll_run_id: int | None = None
    financial_account_id: int | None = None
    posted_only: bool = True


@dataclass(frozen=True, slots=True)
class OperationalReportWarningDTO:
    code: str
    title: str
    message: str


@dataclass(frozen=True, slots=True)
class OperationalReportDetailRowDTO:
    values: tuple[str, ...]
    journal_entry_id: int | None = None
    source_document_type: str | None = None
    source_document_id: int | None = None


@dataclass(frozen=True, slots=True)
class OperationalReportLineDetailDTO:
    title: str
    subtitle: str
    columns: tuple[str, ...]
    rows: tuple[OperationalReportDetailRowDTO, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
