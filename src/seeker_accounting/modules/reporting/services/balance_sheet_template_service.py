from __future__ import annotations

from seeker_accounting.modules.reporting.dto.balance_sheet_template_dto import (
    BalanceSheetTemplateDTO,
)

_DEFAULT_TEMPLATE_CODE = "corporate_classic"

_TEMPLATES: tuple[BalanceSheetTemplateDTO, ...] = (
    BalanceSheetTemplateDTO(
        template_code="corporate_classic",
        template_title="Corporate Classic",
        description=(
            "Formal statutory presentation with restrained spacing and a conservative "
            "hierarchy suited to board packs and official review."
        ),
        standard_note="Statement of Financial Position",
        row_height=28,
        section_background="#F3F4F6",
        subtotal_background="#E5E7EB",
        statement_background="#FFFFFF",
        amount_font_size=11,
        label_font_size=10,
    ),
    BalanceSheetTemplateDTO(
        template_code="statutory_compact",
        template_title="Statutory Compact",
        description=(
            "Dense review layout for finance teams working quickly through formal "
            "balance sheet validation on screen."
        ),
        standard_note="Statement of Financial Position",
        row_height=25,
        section_background="#F8FAFC",
        subtotal_background="#E2E8F0",
        statement_background="#FFFFFF",
        amount_font_size=10,
        label_font_size=9,
    ),
    BalanceSheetTemplateDTO(
        template_code="premium_presentation",
        template_title="Premium Presentation",
        description=(
            "Refined hierarchy with clearer section separation and calmer spacing while "
            "remaining serious accounting software."
        ),
        standard_note="Statement of Financial Position",
        row_height=32,
        section_background="#EEF2FF",
        subtotal_background="#DCE7F7",
        statement_background="#FCFCFD",
        amount_font_size=12,
        label_font_size=11,
    ),
)


class BalanceSheetTemplateService:
    """Presentation-only templates shared by the balance sheet windows."""

    def list_templates(self) -> tuple[BalanceSheetTemplateDTO, ...]:
        return _TEMPLATES

    def get_template(self, template_code: str | None) -> BalanceSheetTemplateDTO:
        normalized = (template_code or "").strip().lower()
        for template in _TEMPLATES:
            if template.template_code == normalized:
                return template
        for template in _TEMPLATES:
            if template.template_code == _DEFAULT_TEMPLATE_CODE:
                return template
        return _TEMPLATES[0]
