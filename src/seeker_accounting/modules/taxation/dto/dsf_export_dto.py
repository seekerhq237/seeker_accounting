"""DTOs for the DSF (Déclaration Statistique et Fiscale) export.

The export produces an annual XLSX workbook whose contents adapt to the
company's DSF form family (``DSF_REAL`` / ``DSF_SIMPLIFIED`` /
``DSF_LIBERATORY``) and tax regime. The shared base sheets are always
present:

* Company profile (NIU, regime, VAT liability, DSF form selection)
* VAT summary (one row per monthly obligation/return in the year)
* VAT detail (every box value across all monthly returns)
* Payments (every payment recorded against the year's returns)
* Readiness (validation results)

Form-family-specific fiches (R1/R2/R3 + simplified / liberatory variants)
are layered on top — see ``DSFExportService._write_form_family_fiches``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GenerateDSFExportCommand:
    fiscal_year: int
    output_path: str


@dataclass(frozen=True, slots=True)
class DSFReadinessIssue:
    severity: str  # "error" | "warning"
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class DSFExportResultDTO:
    company_id: int
    fiscal_year: int
    output_path: str
    sheets_written: tuple[str, ...]
    obligation_count: int
    return_count: int
    payment_count: int
    readiness_issues: tuple[DSFReadinessIssue, ...]
    has_blocking_issues: bool
    # Phase 4 — which DGI form family produced the regime-specific
    # fiches (e.g. ``"DSF_REAL"``). ``None`` when the profile has no
    # form selection or it is set to ``"NONE"``; in that case only the
    # base sheets are written.
    dsf_form_applied: str | None = None
    # Tax regime in force for the export (REAL / SIMPLIFIED / LIBERATORY)
    # captured for audit and downstream display.
    tax_regime_applied: str | None = None
    # Slice T13 — number of withholding-tax certificate rows included
    # on the "Withholding Certificates" sheet. ``0`` when the WHT
    # repository is not wired into the service or the year contains
    # no certificate rows. Voided certificates are still counted (the
    # sheet shows them for audit) but are flagged separately.
    withholding_certificate_count: int = 0
