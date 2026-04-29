"""Receipt Allocation Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.receipt_allocation import state_keys as K
from seeker_accounting.modules.wizards.receipt_allocation.advisor import (
    build_receipt_allocation_advisor,
)
from seeker_accounting.modules.wizards.receipt_allocation.steps.allocate_step import (
    AllocateStep,
)
from seeker_accounting.modules.wizards.receipt_allocation.steps.confirm_step import (
    ConfirmStep,
)
from seeker_accounting.modules.wizards.receipt_allocation.steps.header_step import (
    HeaderStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "receipt_allocation"


@dataclass(slots=True)
class ReceiptAllocationResult:
    completed: bool
    receipt_id: int | None
    receipt_status: str | None
    posted_journal_entry_id: int | None
    wizard_run_id: int | None


class ReceiptAllocationWizard:
    @staticmethod
    def steps_factory():
        return [HeaderStep(), AllocateStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_receipt_allocation_advisor()


def launch_receipt_allocation_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> ReceiptAllocationResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Receipt & Allocation",
        intro=(
            "Capture a customer receipt, allocate it across open invoices, "
            "and optionally post it to the GL in one flow."
        ),
        steps_factory=ReceiptAllocationWizard.steps_factory,
        advisor_factory=ReceiptAllocationWizard.advisor_factory,
        feature_label="Receipt Allocation",
        parent=parent,
    )
    if outcome is None:
        return ReceiptAllocationResult(False, None, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    rid = outcome.state.get(K.KEY_RECEIPT_ID)
    je = outcome.state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)
    return ReceiptAllocationResult(
        completed=outcome.completed,
        receipt_id=int(rid) if isinstance(rid, int) else None,
        receipt_status=outcome.state.get(K.KEY_RECEIPT_STATUS),
        posted_journal_entry_id=int(je) if isinstance(je, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
