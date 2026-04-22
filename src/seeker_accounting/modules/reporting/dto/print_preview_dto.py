from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PrintPreviewRowDTO:
    row_type: str
    reference_code: str | None
    label: str
    amount_text: str | None = None
    secondary_amount_text: str | None = None
    tertiary_amount_text: str | None = None
    quaternary_amount_text: str | None = None


@dataclass(frozen=True, slots=True)
class PrintPreviewMetaDTO:
    """Metadata passed to the print-preview dialog framework."""

    report_title: str
    company_name: str
    period_label: str
    generated_at: str
    filter_summary: str
    template_title: str | None = None
    amount_headers: tuple[str, ...] = ("Amount",)
    rows: tuple[PrintPreviewRowDTO, ...] = field(default_factory=tuple)
