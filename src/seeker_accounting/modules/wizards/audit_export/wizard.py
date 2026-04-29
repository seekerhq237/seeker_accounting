"""Audit Export wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.audit.dto.audit_export_dto import AuditExportResultDTO
from seeker_accounting.modules.wizards.audit_export import state_keys as K
from seeker_accounting.modules.wizards.audit_export.advisor import (
    build_audit_export_advisor,
)
from seeker_accounting.modules.wizards.audit_export.steps.export_step import ExportStep
from seeker_accounting.modules.wizards.audit_export.steps.preview_step import PreviewStep
from seeker_accounting.modules.wizards.audit_export.steps.setup_step import SetupStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "audit_export"


@dataclass(slots=True)
class AuditExportResult:
    completed: bool
    result: AuditExportResultDTO | None
    wizard_run_id: int | None


class AuditExportWizard:
    @staticmethod
    def steps_factory():
        return [SetupStep(), PreviewStep(), ExportStep()]

    @staticmethod
    def advisor_factory():
        return build_audit_export_advisor()


def launch_audit_export_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> AuditExportResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Audit Export",
        intro=(
            "Package posted journal entries, journal lines, and the audit "
            "event log into a self-contained CSV bundle for handover to an "
            "external auditor. The manifest includes SHA-256 checksums so "
            "the auditor can verify integrity."
        ),
        steps_factory=AuditExportWizard.steps_factory,
        advisor_factory=AuditExportWizard.advisor_factory,
        feature_label="Audit Export",
        parent=parent,
    )
    if outcome is None:
        return AuditExportResult(False, None, None)
    assert isinstance(outcome, WizardOutcome)
    result = outcome.state.get(K.KEY_RESULT)
    return AuditExportResult(
        completed=outcome.completed,
        result=result if isinstance(result, AuditExportResultDTO) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
