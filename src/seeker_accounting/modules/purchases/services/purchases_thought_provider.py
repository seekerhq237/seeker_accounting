"""Purchases-domain ambient thoughts.

Mirrors the sales provider in shape: a small rule set anchored in
context the shell already has, plus one page-context hint for drafts.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.shared.dto.ambient_thought_dto import (
    AmbientThoughtContextDTO,
    AmbientThoughtDTO,
)


if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry


_PURCHASES_NAV_IDS = {
    nav_ids.PURCHASE_BILLS,
    nav_ids.PURCHASE_ORDERS,
    nav_ids.PURCHASE_CREDIT_NOTES,
    nav_ids.SUPPLIER_PAYMENTS,
}


class PurchasesThoughtProvider:
    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> list[AmbientThoughtDTO]:
        if context.nav_id not in _PURCHASES_NAV_IDS:
            return []

        thoughts: list[AmbientThoughtDTO] = []

        status = (context.fiscal_period_status or "").lower()
        if status in ("closing", "locked"):
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="purchases.period.closing",
                    tone="caution",
                    summary=(
                        "The active fiscal period is closing — posting may be restricted soon."
                        if status == "closing"
                        else "The active fiscal period is locked."
                    ),
                    detail=(
                        "New supplier bills can still be drafted, but posting "
                        "into this period may be blocked."
                    ),
                    confidence_label="High confidence",
                    relevance=0.85,
                    urgency=0.7 if status == "closing" else 0.4,
                    confidence=0.95,
                    importance=0.8,
                    source_kind="rule",
                    nav_id=context.nav_id,
                    why_items=(
                        f"Active period status: {status}.",
                        "Posting is governed by period control rules.",
                    ),
                )
            )

        if context.page_value("has_line_without_tax") is True:
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="purchases.bill.line_missing_tax",
                    tone="hint",
                    summary="A line on this bill has no tax code.",
                    detail=(
                        "Recoverable VAT may be at risk if the tax code is "
                        "missing on supplier-side lines."
                    ),
                    confidence_label="Watch",
                    relevance=0.95,
                    urgency=0.3,
                    confidence=0.8,
                    importance=0.6,
                    source_kind="rule",
                    nav_id=context.nav_id,
                    why_items=("At least one line has no tax code selected.",),
                )
            )

        if context.page_value("supplier_tax_details_incomplete") is True:
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="purchases.supplier.tax_incomplete",
                    tone="caution",
                    summary="Recoverable VAT may be at risk: supplier tax details are incomplete.",
                    detail=(
                        "The selected supplier is missing required tax registration "
                        "fields. Recoverability rules typically require a complete profile."
                    ),
                    confidence_label="Likely",
                    relevance=0.9,
                    urgency=0.4,
                    confidence=0.7,
                    importance=0.7,
                    source_kind="rule",
                    nav_id=context.nav_id,
                    why_items=("Supplier tax registration profile is incomplete.",),
                )
            )

        return thoughts
