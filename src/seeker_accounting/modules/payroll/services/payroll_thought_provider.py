"""Payroll-domain ambient thoughts.

Phase 2 rule set focuses on the highest-confidence payroll signals:

* `payroll.deadline.approaching` — a remittance deadline is within
  the next 7 days. Drawn from `PayrollRemittanceDeadlineService`,
  which already encodes the DGI/CNPS rule for the 15th-of-next-month
  deadline.
* `payroll.deadline.overdue` — at least one remittance is already past
  its deadline. Surfaces with caution tone regardless of nav.
* `payroll.statutory.pack_unverified` — leverages
  `PayrollOutputWarningService` to surface unverified statutory pack
  warnings while the user is on a payroll page.

Every thought is rule-derived; no ML. Each carries `why_items` so the
overlay's Why panel can show the user the underlying evidence.
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


_PAYROLL_NAV_IDS = {
    nav_ids.PAYROLL_SETUP,
    nav_ids.PAYROLL_CALCULATION,
    "payroll_accounting",
    "payroll_operations",
}


class PayrollThoughtProvider:
    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> list[AmbientThoughtDTO]:
        if context.company_id is None:
            return []

        thoughts: list[AmbientThoughtDTO] = []

        # Boost relevance when the user is on a payroll-flavoured page.
        on_payroll_page = (context.nav_id or "") in _PAYROLL_NAV_IDS or (
            context.nav_id or ""
        ).startswith("payroll_")
        relevance = 0.85 if on_payroll_page else 0.4

        try:
            deadlines = (
                self._sr.payroll_remittance_deadline_service.get_outstanding_deadlines(
                    context.company_id
                )
            )
        except Exception:
            logger.debug(
                "PayrollThoughtProvider: deadline lookup failed.", exc_info=True
            )
            deadlines = []

        overdue = [d for d in deadlines if d.is_overdue]
        soon = [
            d
            for d in deadlines
            if not d.is_overdue
            and d.days_until_deadline is not None
            and 0 <= d.days_until_deadline <= 7
        ]

        if overdue:
            first = overdue[0]
            why = [
                f"{first.authority_label} batch {first.batch_number} is past its deadline.",
                f"Outstanding amount: {first.outstanding}.",
            ]
            if len(overdue) > 1:
                why.append(f"{len(overdue) - 1} other remittance(s) are also overdue.")
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="payroll.deadline.overdue",
                    tone="caution",
                    summary="A payroll remittance is already past its filing deadline.",
                    detail=(
                        f"{first.authority_label} batch {first.batch_number} was due on "
                        f"{first.filing_deadline}."
                    ),
                    confidence_label="High confidence",
                    relevance=relevance,
                    urgency=0.95,
                    confidence=0.95,
                    importance=0.9,
                    source_kind="deadline",
                    nav_id=context.nav_id,
                    why_items=tuple(why),
                )
            )
        elif soon:
            first = soon[0]
            days = first.days_until_deadline or 0
            label = "today" if days == 0 else (
                "tomorrow" if days == 1 else f"in {days} days"
            )
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="payroll.deadline.approaching",
                    tone="projection",
                    summary=(
                        f"A {first.authority_code.upper()} remittance is due {label}."
                    ),
                    detail=(
                        f"{first.authority_label} batch {first.batch_number} is due on "
                        f"{first.filing_deadline}."
                    ),
                    confidence_label="High confidence",
                    relevance=relevance,
                    urgency=max(0.4, 1.0 - (days / 10.0)),
                    confidence=0.9,
                    importance=0.8,
                    source_kind="deadline",
                    nav_id=context.nav_id,
                    why_items=(
                        f"Filing deadline: {first.filing_deadline}.",
                        f"Outstanding amount: {first.outstanding}.",
                    ),
                )
            )

        # Statutory pack warnings — only surface while the user is on a
        # payroll page, otherwise this is noise.
        if on_payroll_page:
            try:
                warnings = self._sr.payroll_output_warning_service.get_export_warnings(
                    context.company_id
                )
            except Exception:
                logger.debug(
                    "PayrollThoughtProvider: warning lookup failed.", exc_info=True
                )
                warnings = []
            if warnings:
                first = warnings[0]
                thoughts.append(
                    AmbientThoughtDTO(
                        thought_code="payroll.statutory.pack_warning",
                        tone="hint",
                        summary=first.title or "Payroll setup warning.",
                        detail=first.message or "",
                        confidence_label="Watch",
                        relevance=0.8,
                        urgency=0.2,
                        confidence=0.7,
                        importance=0.5,
                        source_kind="rule",
                        nav_id=context.nav_id,
                        why_items=(first.message or "",),
                    )
                )

        return thoughts
