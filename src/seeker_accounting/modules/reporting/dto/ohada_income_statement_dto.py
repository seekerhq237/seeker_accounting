from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OhadaCoverageWarningDTO:
    code: str
    title: str
    message: str
    affected_line_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OhadaAccountContributionDTO:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    line_code: str | None
    line_label: str | None
    debit_amount: Decimal
    credit_amount: Decimal
    signed_amount: Decimal


@dataclass(frozen=True, slots=True)
class OhadaIncomeStatementLineDTO:
    code: str
    label: str
    section_code: str
    section_title: str
    signed_amount: Decimal
    display_order: int
    is_formula: bool
    can_drilldown: bool
    prefixes: tuple[str, ...] = ()
    formula_components: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OhadaIncomeStatementLineDetailDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    line_code: str
    line_label: str
    signed_amount: Decimal
    accounts: tuple[OhadaAccountContributionDTO, ...]
    warnings: tuple[OhadaCoverageWarningDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class OhadaIncomeStatementReportDTO:
    company_id: int
    date_from: date | None
    date_to: date | None
    spec_version: str
    lines: tuple[OhadaIncomeStatementLineDTO, ...]
    warnings: tuple[OhadaCoverageWarningDTO, ...]
    unclassified_accounts: tuple[OhadaAccountContributionDTO, ...] = ()
    has_chart_coverage: bool = False
    has_posted_activity: bool = False
    has_classified_activity: bool = False
    highlight_line_codes: tuple[str, ...] = field(default_factory=tuple)
