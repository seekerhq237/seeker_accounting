"""Document Numbering Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.document_numbering import state_keys as K
from seeker_accounting.modules.wizards.document_numbering.advisor import (
    build_document_numbering_advisor,
)
from seeker_accounting.modules.wizards.document_numbering.steps.commit_step import CommitStep
from seeker_accounting.modules.wizards.document_numbering.steps.configure_step import (
    ConfigureStep,
)
from seeker_accounting.modules.wizards.document_numbering.steps.pick_step import PickStep
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "document_numbering"


@dataclass(slots=True)
class DocumentNumberingResult:
    completed: bool
    sequence_id: int | None
    preview_number: str | None
    wizard_run_id: int | None


class DocumentNumberingWizard:
    @staticmethod
    def steps_factory():
        return [PickStep(), ConfigureStep(), CommitStep()]

    @staticmethod
    def advisor_factory():
        return build_document_numbering_advisor()


def launch_document_numbering_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> DocumentNumberingResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Document Numbering",
        intro=(
            "Configure how document numbers are generated for invoices, bills, "
            "journals and other document types."
        ),
        steps_factory=DocumentNumberingWizard.steps_factory,
        advisor_factory=DocumentNumberingWizard.advisor_factory,
        feature_label="Document Numbering",
        parent=parent,
    )
    if outcome is None:
        return DocumentNumberingResult(False, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    sid = outcome.state.get(K.KEY_SEQUENCE_ID)
    pn = outcome.state.get(K.KEY_PREVIEW_NUMBER)
    return DocumentNumberingResult(
        completed=outcome.completed,
        sequence_id=int(sid) if isinstance(sid, int) else None,
        preview_number=str(pn) if pn else None,
        wizard_run_id=outcome.wizard_run_id,
    )
