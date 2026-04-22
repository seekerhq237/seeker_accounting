"""DTOs for payroll export operations — PDF payslips, CSV summaries."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PayslipExportResultDTO:
    """Result of a single payslip PDF export."""
    file_path: str
    employee_number: str
    employee_display_name: str
    run_reference: str
    period_label: str


@dataclass(frozen=True, slots=True)
class PayslipBatchExportResultDTO:
    """Result of a batch payslip PDF export."""
    output_directory: str
    exported: tuple[PayslipExportResultDTO, ...]
    failed: tuple[tuple[str, str], ...]  # (employee_display_name, error_message)


@dataclass(frozen=True, slots=True)
class SummaryExportResultDTO:
    """Result of a payroll summary export (CSV or PDF)."""
    file_path: str
    format: str  # "csv" or "pdf"
    run_reference: str
    period_label: str
    employee_count: int


@dataclass(frozen=True, slots=True)
class PayrollOutputWarningDTO:
    """A non-blocking compliance/quality warning for export contexts."""
    code: str
    severity: str  # "info" or "warning"
    title: str
    message: str
