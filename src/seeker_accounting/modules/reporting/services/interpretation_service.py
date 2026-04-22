from __future__ import annotations

from seeker_accounting.modules.reporting.dto.insight_card_dto import InsightCardDTO
from seeker_accounting.modules.reporting.dto.interpretation_dto import (
    InterpretationItemDTO,
    InterpretationPanelDTO,
)


class InterpretationService:
    """Transforms ranked insight cards into compact interpretation panels."""

    def build_panel(
        self,
        *,
        title: str,
        subtitle: str | None,
        insights: tuple[InsightCardDTO, ...],
        limit: int = 3,
    ) -> InterpretationPanelDTO:
        items = tuple(
            InterpretationItemDTO(
                interpretation_code=card.insight_code,
                title=card.title,
                message=card.statement,
                basis_text=" | ".join(f"{item.label}: {item.value_text}" for item in card.numeric_basis),
                severity_code=card.severity_code,
                detail_key=card.detail_key,
            )
            for card in insights[:limit]
        )
        return InterpretationPanelDTO(title=title, subtitle=subtitle, items=items)
