"""Treasury-domain ambient thoughts.

Initial signals:

* `treasury.period.closing` — same period-state caution as the other
  posting modules.
* `treasury.payment.cash_impact` — page-level cash-impact hint, opted
  into by treasury pages via ``get_ambient_context``.
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


_TREASURY_NAV_IDS = {
    nav_ids.FINANCIAL_ACCOUNTS,
    nav_ids.TREASURY_TRANSACTIONS,
    nav_ids.TREASURY_TRANSFERS,
    nav_ids.STATEMENT_LINES,
    nav_ids.BANK_RECONCILIATION,
}


class TreasuryThoughtProvider:
    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> list[AmbientThoughtDTO]:
        if context.nav_id not in _TREASURY_NAV_IDS:
            return []

        thoughts: list[AmbientThoughtDTO] = []

        status = (context.fiscal_period_status or "").lower()
        if status in ("closing", "locked"):
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="treasury.period.closing",
                    tone="caution",
                    summary=(
                        "The active fiscal period is closing — posting may be restricted soon."
                        if status == "closing"
                        else "The active fiscal period is locked."
                    ),
                    detail=(
                        "Cash transactions and transfers post into the active "
                        "period; new postings may be blocked once it locks."
                    ),
                    confidence_label="High confidence",
                    relevance=0.8,
                    urgency=0.6 if status == "closing" else 0.4,
                    confidence=0.95,
                    importance=0.7,
                    source_kind="rule",
                    nav_id=context.nav_id,
                    why_items=(
                        f"Active period status: {status}.",
                        "Posting is governed by period control rules.",
                    ),
                )
            )

        if context.page_value("payment_would_overdraw") is True:
            account = str(context.page_value("payment_account_label") or "this account")
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="treasury.payment.would_overdraw",
                    tone="caution",
                    summary=f"This payment would push {account} below zero.",
                    detail=(
                        "Available balance after posting this payment is projected "
                        "to be negative. Consider sequencing or a transfer first."
                    ),
                    confidence_label="Likely",
                    relevance=0.95,
                    urgency=0.7,
                    confidence=0.8,
                    importance=0.85,
                    source_kind="rule",
                    nav_id=context.nav_id,
                    why_items=("Projected balance after this payment is below zero.",),
                )
            )

        return thoughts
