from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CalcStepDTO:
    id: int
    sequence_number: int
    stage_code: str
    component_id: int | None
    component_code: str | None
    component_name: str | None
    formula_code: str
    input_json: str | None
    output_json: str | None
    amount: Decimal
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class PayrollVarianceLineDTO:
    category_code: str
    subject_code: str
    subject_label: str
    prior_amount: Decimal
    current_amount: Decimal
    delta_amount: Decimal
    delta_percent: Decimal | None
    severity_code: str
    explanation: str


@dataclass(frozen=True, slots=True)
class PayrollVarianceAnalysisDTO:
    run_id: int
    run_reference: str
    prior_run_id: int | None
    prior_run_reference: str | None
    threshold_percent: Decimal
    lines: tuple[PayrollVarianceLineDTO, ...]

    @property
    def has_warnings(self) -> bool:
        return any(line.severity_code in {"warning", "critical"} for line in self.lines)


@dataclass(frozen=True, slots=True)
class PayrollDryRunReportResultDTO:
    file_path: str
    format: str
    run_id: int
    run_reference: str
    warning_count: int
