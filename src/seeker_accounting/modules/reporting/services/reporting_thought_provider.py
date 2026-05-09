"""Reporting-domain ambient thoughts.

Surfaces actionable nudges when the user is in reporting or analytics
views.  Rules are grounded in fiscal period state and navigation
context — no heavy report queries are issued during ambient refresh.

Codes produced
--------------
reporting.period.closing_affects_reports
    Caution when the active fiscal period is closing and the user is on
    a reporting page — unreported transactions from this period should
    be posted before period lock.

reporting.reports.post_before_running
    Gentle hint on the main reports page reminding the user that
    management reports reflect posted transactions only.

reporting.audit_log.periodic_review
    Low-priority reminder when on the Audit Log page that regular
    review is good governance practice.

reporting.project_variance.action_recommended
    When on the project variance page and the period is closing, a
    reminder that project cost postings should be finalised.
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


_REPORTING_NAV = {
    nav_ids.REPORTS,
    nav_ids.PROJECT_VARIANCE_ANALYSIS,
    nav_ids.CONTRACT_SUMMARY,
    nav_ids.INVENTORY_REPORTS,
}
_AUDIT_NAV = {nav_ids.AUDIT_LOG}


class ReportingThoughtProvider:
    def __init__(self, service_registry: "ServiceRegistry") -> None:
        self._sr = service_registry

    def provide(
        self, context: AmbientThoughtContextDTO
    ) -> list[AmbientThoughtDTO]:
        nav = context.nav_id
        if nav not in _REPORTING_NAV and nav not in _AUDIT_NAV:
            return []

        thoughts: list[AmbientThoughtDTO] = []
        status = (context.fiscal_period_status or "").lower()

        # ── Period-closing caution on reporting pages ─────────────────
        if nav in _REPORTING_NAV and status in ("closing", "locked"):
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="reporting.period.closing_affects_reports",
                    tone="caution",
                    summary=(
                        "The active period is closing — ensure all transactions are "
                        "posted before running final reports."
                        if status == "closing"
                        else "The active period is locked — reports now reflect final posted data."
                    ),
                    detail=(
                        "Management reports, trial balances, and the P&L read from "
                        "posted journal entries only. Drafts are excluded. "
                        + ("Post any pending documents before locking the period."
                           if status == "closing"
                           else "No further postings can be added to this period.")
                    ),
                    confidence_label="High confidence",
                    relevance=0.85,
                    urgency=0.75 if status == "closing" else 0.3,
                    confidence=0.95,
                    importance=0.8,
                    source_kind="rule",
                    nav_id=nav,
                    why_items=(
                        f"Active fiscal period status: {status}.",
                        "Reports exclude draft/unposted transactions.",
                    ),
                )
            )

        # ── General posting-completeness hint on the main reports page ─
        if nav == nav_ids.REPORTS and status == "open":
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="reporting.reports.post_before_running",
                    tone="hint",
                    summary="Management reports reflect posted transactions only — drafts are excluded.",
                    detail=(
                        "Before running period-end reports, confirm that all "
                        "invoices, bills, payroll runs, and treasury transactions "
                        "have been posted into the active period."
                    ),
                    confidence_label="Watch",
                    relevance=0.5,
                    urgency=0.15,
                    confidence=0.85,
                    importance=0.55,
                    source_kind="rule",
                    nav_id=nav,
                    why_items=(
                        "Reports page is active.",
                        "Unposted documents are excluded from GL-based reports.",
                    ),
                )
            )

        # ── Project variance: finalise postings reminder on period close ─
        if nav == nav_ids.PROJECT_VARIANCE_ANALYSIS and status in ("closing", "locked"):
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="reporting.project_variance.action_recommended",
                    tone="caution",
                    summary=(
                        "Project cost postings should be finalised before the period closes."
                    ),
                    detail=(
                        "Variance analysis compares budgeted versus posted project "
                        "costs. Unposted cost allocations will not appear in variance "
                        "reports for this period."
                    ),
                    confidence_label="Likely",
                    relevance=0.75,
                    urgency=0.6,
                    confidence=0.85,
                    importance=0.7,
                    source_kind="rule",
                    nav_id=nav,
                    why_items=(
                        f"Active period status: {status}.",
                        "Project variance reads from posted cost allocations.",
                    ),
                )
            )

        # ── Audit log: periodic review reminder ───────────────────────
        if nav in _AUDIT_NAV:
            thoughts.append(
                AmbientThoughtDTO(
                    thought_code="reporting.audit_log.periodic_review",
                    tone="hint",
                    summary="Regular audit log review is a good governance practice.",
                    detail=(
                        "The audit log records all create, update, and delete "
                        "actions across accounting documents. Periodic review "
                        "helps detect errors and confirms segregation of duties."
                    ),
                    confidence_label="Watch",
                    relevance=0.4,
                    urgency=0.05,
                    confidence=0.6,
                    importance=0.45,
                    source_kind="rule",
                    nav_id=nav,
                    why_items=(
                        "Audit Log page is active.",
                        "Periodic review supports internal control compliance.",
                    ),
                )
            )

        return thoughts
