"""Audit coverage catalog for state transitions, overrides, and business steps."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditEventRequirement:
    event_type_code: str
    module_code: str
    category: str
    description: str


DEFAULT_AUDIT_REQUIREMENTS: tuple[AuditEventRequirement, ...] = (
    AuditEventRequirement("STATE_TRANSITION", "platform", "state", "Every persisted lifecycle transition records before and after states."),
    AuditEventRequirement("OVERRIDE_APPLIED", "platform", "override", "Every permissioned override records actor, reason, and affected entity."),
    AuditEventRequirement("BUSINESS_PROCESS_STEP", "platform", "bp_step", "Each long-running guided workflow records significant step completion."),
    AuditEventRequirement("PAYROLL_CORRECTION_CREATED", "payroll", "state", "Payroll correction facts are audited when queued."),
    AuditEventRequirement("PAYROLL_CORRECTION_APPLIED", "payroll", "state", "Payroll correction facts are audited when applied to a run."),
    AuditEventRequirement("PAYROLL_RUN_REVERSED", "payroll", "state", "Payroll run reversal is audited with source and reversal entry references."),
)


@dataclass(frozen=True, slots=True)
class AuditCoverageReport:
    required: tuple[AuditEventRequirement, ...]
    observed_event_type_codes: tuple[str, ...]

    @property
    def missing_event_type_codes(self) -> tuple[str, ...]:
        observed = set(self.observed_event_type_codes)
        return tuple(
            req.event_type_code
            for req in self.required
            if req.event_type_code not in observed
        )

    @property
    def is_complete(self) -> bool:
        return not self.missing_event_type_codes


def build_audit_coverage_report(
    observed_event_type_codes: set[str] | tuple[str, ...] | list[str],
    *,
    requirements: tuple[AuditEventRequirement, ...] = DEFAULT_AUDIT_REQUIREMENTS,
) -> AuditCoverageReport:
    return AuditCoverageReport(
        required=requirements,
        observed_event_type_codes=tuple(sorted(set(observed_event_type_codes))),
    )