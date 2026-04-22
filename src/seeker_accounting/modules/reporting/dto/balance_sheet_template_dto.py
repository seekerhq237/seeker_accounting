from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BalanceSheetTemplateDTO:
    template_code: str
    template_title: str
    description: str
    standard_note: str
    row_height: int
    section_background: str
    subtotal_background: str
    statement_background: str
    amount_font_size: int
    label_font_size: int
