"""Tax-domain ambient thoughts.

Initial signals operate on shell context only:

* `tax.profile.missing` — when on a tax page and the company has no
  tax profile configured. Detected by attempting a profile read; any
  failure or empty result is treated as "missing".
* `tax.period.closing` — generic period-state caution while on a tax
  page (e.g. tax codes setup, tax compliance).

Future phases can add filing-window proximity once a structured
fiscal-deadline source exists.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.shared.dto.ambient_thought_dto import (
    AmbientThoughtContextDTO,
    AmbientThoughtDTO,
)


if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry


logger = logging.getLogger(__name__)


_TAX_NAV_IDS = {
    nav_ids.TAX_CODES,
    nav_ids.TAX_PROFILE,
    nav_ids.TAX_COMPLIANCE,
    nav_ids.TAX_DASHBOARD,
    nav_ids.TAX_AUDIT_TRAIL,
    nav_ids.WITHHOLDING_CERTIFICATES,
}


class TaxThoughtProvider:
    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> list[AmbientThoughtDTO]:
        if context.nav_id not in _TAX_NAV_IDS or context.company_id is None:
            return []

        thoughts: list[AmbientThoughtDTO] = []

        # Profile-readiness probe — best-effort; if the service raises or
        # returns nothing usable, we treat it as "missing" only when the
        # user is specifically on the tax profile page (low-noise default).
        if context.nav_id == nav_ids.TAX_PROFILE:
            profile_missing = False
            try:
                profile = self._sr.company_tax_profile_service.get_or_default(
                    context.company_id
                )
                if profile is None or not getattr(profile, "exists", False):
                    profile_missing = True
                elif not getattr(profile, "niu", None):
                    profile_missing = True
            except Exception:
                logger.debug(
                    "TaxThoughtProvider: profile lookup failed.", exc_info=True
                )
                profile_missing = True

            if profile_missing:
                thoughts.append(
                    AmbientThoughtDTO(
                        thought_code="tax.profile.missing",
                        tone="hint",
                        summary="This company's tax profile looks incomplete.",
                        detail=(
                            "A complete tax profile (regime, NIU, jurisdiction) is "
                            "required before tax obligations and DSF exports can be "
                            "produced reliably."
                        ),
                        confidence_label="Watch",
                        relevance=0.95,
                        urgency=0.3,
                        confidence=0.7,
                        importance=0.7,
                        source_kind="rule",
                        nav_id=context.nav_id,
                        why_items=(
                            "Tax identification number is missing or the profile is empty.",
                        ),
                    )
                )

        status = (context.fiscal_period_status or "").lower()
        if status in ("closing", "locked"):
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="tax.period.closing",
                    tone="caution",
                    summary=(
                        "The active fiscal period is closing."
                        if status == "closing"
                        else "The active fiscal period is locked."
                    ),
                    detail=(
                        "Tax adjustments dated in this period may be blocked once "
                        "it is fully locked."
                    ),
                    confidence_label="High confidence",
                    relevance=0.7,
                    urgency=0.5 if status == "closing" else 0.3,
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

        return thoughts
