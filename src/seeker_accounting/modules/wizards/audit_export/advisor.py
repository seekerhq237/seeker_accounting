"""Advisor for the Audit Export wizard."""
from __future__ import annotations

from datetime import date, timedelta

from seeker_accounting.modules.audit.dto.audit_export_dto import (
    AuditExportPreviewDTO,
    AuditExportResultDTO,
)
from seeker_accounting.modules.wizards.audit_export import state_keys as K
from seeker_accounting.platform.wizards import (
    AdvisorMessage,
    AdvisorSeverity,
    WizardAdvisor,
    WizardContext,
    WizardState,
)

_LARGE_RANGE_DAYS = 366 * 3  # warn if export covers more than ~3 years
_LARGE_VOLUME_LINES = 100_000


def _setup_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    messages: list[AdvisorMessage] = [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Use a fresh, empty folder",
            detail="Pick a new folder for each export so files from previous "
                   "runs do not get overwritten or mixed in.",
        )
    ]
    from_d = state.get(K.KEY_FROM_DATE)
    to_d = state.get(K.KEY_TO_DATE)
    if isinstance(from_d, date) and isinstance(to_d, date):
        span = to_d - from_d
        if span > timedelta(days=_LARGE_RANGE_DAYS):
            messages.append(
                AdvisorMessage(
                    severity=AdvisorSeverity.WARNING,
                    title="Large date range",
                    detail=f"You are exporting {span.days} days of data. "
                           "Consider splitting by fiscal year for easier handover.",
                )
            )
    if state.get(K.KEY_INCLUDE_AUDIT_EVENTS) is False:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Audit events excluded",
                detail="External auditors usually expect the audit event log "
                       "alongside accounting truth. Re-enable it unless you have "
                       "a specific reason.",
            )
        )
    return messages


def _preview_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    preview = state.get(K.KEY_PREVIEW)
    if not isinstance(preview, AuditExportPreviewDTO):
        return []
    messages: list[AdvisorMessage] = []
    if preview.posted_journal_entry_count == 0:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.WARNING,
                title="No posted journal entries in range",
                detail="The package would only contain headers. Verify the date "
                       "range and that journal entries for that period are posted.",
            )
        )
    if preview.posted_journal_line_count > _LARGE_VOLUME_LINES:
        messages.append(
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Large package",
                detail=f"Export will write {preview.posted_journal_line_count:,} "
                       "journal lines. Make sure the destination folder has "
                       "enough free space.",
            )
        )
    return messages


def _export_rules(ctx: WizardContext, state: WizardState) -> list[AdvisorMessage]:
    result = state.get(K.KEY_RESULT)
    if not isinstance(result, AuditExportResultDTO):
        return [
            AdvisorMessage(
                severity=AdvisorSeverity.INFO,
                title="Run the export",
                detail="Use the <i>Run export now</i> button to write the package "
                       "to the chosen folder.",
            )
        ]
    return [
        AdvisorMessage(
            severity=AdvisorSeverity.INFO,
            title="Hand over the entire folder",
            detail="Send the whole output folder — including <code>manifest.json</code> "
                   "— to the auditor. The manifest contains SHA-256 checksums that "
                   "let them verify integrity.",
        )
    ]


def build_audit_export_advisor() -> WizardAdvisor:
    advisor = WizardAdvisor(wizard_code="audit_export")
    advisor.register("setup", _setup_rules)
    advisor.register("preview", _preview_rules)
    advisor.register("export", _export_rules)
    return advisor
