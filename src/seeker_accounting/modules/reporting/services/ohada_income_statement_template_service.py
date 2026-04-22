from __future__ import annotations

from seeker_accounting.modules.reporting.dto.ohada_income_statement_template_dto import (
    OhadaIncomeStatementTemplateDTO,
)

_DEFAULT_TEMPLATE_CODE = "corporate_classic"

_TEMPLATES: tuple[OhadaIncomeStatementTemplateDTO, ...] = (
    OhadaIncomeStatementTemplateDTO(
        template_code="corporate_classic",
        template_title="Corporate Classic",
        description=(
            "Formal statutory presentation with restrained spacing and a conservative "
            "hierarchy suited to board packs and official review."
        ),
        standard_note="SYSCOHADA Rev. 2017",
        row_height=28,
        section_background="#F3F4F6",
        subtotal_background="#E5E7EB",
        statement_background="#FFFFFF",
        amount_font_size=11,
        label_font_size=10,
    ),
    OhadaIncomeStatementTemplateDTO(
        template_code="compact_management",
        template_title="Compact Management",
        description=(
            "Dense on-screen review layout with tighter rows and calmer spacing for "
            "finance teams working quickly through period results."
        ),
        standard_note="SYSCOHADA Rev. 2017",
        row_height=24,
        section_background="#F8FAFC",
        subtotal_background="#E2E8F0",
        statement_background="#FFFFFF",
        amount_font_size=10,
        label_font_size=9,
    ),
    OhadaIncomeStatementTemplateDTO(
        template_code="premium_presentation",
        template_title="Premium Presentation",
        description=(
            "Refined visual hierarchy with stronger section emphasis and more breathing "
            "room while remaining formal and accounting-first."
        ),
        standard_note="SYSCOHADA Rev. 2017",
        row_height=32,
        section_background="#EEF2FF",
        subtotal_background="#DCE7F7",
        statement_background="#FCFCFD",
        amount_font_size=12,
        label_font_size=11,
    ),
)


class OhadaIncomeStatementTemplateService:
    """Presentation-only template metadata for the OHADA statement."""

    def list_templates(self) -> tuple[OhadaIncomeStatementTemplateDTO, ...]:
        return _TEMPLATES

    def get_template(self, template_code: str | None) -> OhadaIncomeStatementTemplateDTO:
        normalized = (template_code or "").strip().lower()
        for template in _TEMPLATES:
            if template.template_code == normalized:
                return template
        for template in _TEMPLATES:
            if template.template_code == _DEFAULT_TEMPLATE_CODE:
                return template
        return _TEMPLATES[0]
