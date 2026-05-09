"""Sales-domain ambient thoughts.

Initial rule set is intentionally small and high-signal:

* `sales.invoice.locked_period` — when the user is creating/editing
  a sales invoice and the active fiscal period is `closing` or
  `locked`, surface a caution. The provider relies on context only;
  it does not query the DB.

Future phases should add anomaly detection (tax outliers, due-date
deviations) once we have enough customer history to baseline.
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


_SALES_NAV_IDS = {
    nav_ids.SALES_INVOICES,
    nav_ids.SALES_ORDERS,
    nav_ids.SALES_CREDIT_NOTES,
    nav_ids.CUSTOMER_QUOTES,
    nav_ids.CUSTOMER_RECEIPTS,
}


class SalesThoughtProvider:
    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> list[AmbientThoughtDTO]:
        if context.nav_id not in _SALES_NAV_IDS:
            return []

        thoughts: list[AmbientThoughtDTO] = []

        status = (context.fiscal_period_status or "").lower()
        if status in ("closing", "locked"):
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="sales.period.closing",
                    tone="caution",
                    summary=(
                        "The active fiscal period is closing — posting may be restricted soon."
                        if status == "closing"
                        else "The active fiscal period is locked."
                    ),
                    detail=(
                        "Drafts can still be saved, but posting will be blocked once "
                        "the period is fully locked."
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

        # Page-level hint: a draft invoice flagged as having no tax code
        # on at least one line. Pages opt in by exposing
        # ``get_ambient_context`` returning ``{"has_line_without_tax": True}``.
        if context.page_value("has_line_without_tax") is True:
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="sales.invoice.line_missing_tax",
                    tone="hint",
                    summary="A line on this draft has no tax code.",
                    detail=(
                        "Lines without a tax code post at zero VAT, which may not "
                        "reflect this customer's tax profile."
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

        return thoughts
