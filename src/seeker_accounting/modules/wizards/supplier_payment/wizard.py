"""Supplier Payment Wizard launcher."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.wizards.supplier_payment import state_keys as K
from seeker_accounting.modules.wizards.supplier_payment.advisor import (
    build_supplier_payment_advisor,
)
from seeker_accounting.modules.wizards.supplier_payment.steps.allocate_step import (
    AllocateStep,
)
from seeker_accounting.modules.wizards.supplier_payment.steps.confirm_step import (
    ConfirmStep,
)
from seeker_accounting.modules.wizards.supplier_payment.steps.header_step import (
    HeaderStep,
)
from seeker_accounting.platform.wizards import WizardOutcome, launch_wizard

WIZARD_CODE = "supplier_payment"


@dataclass(slots=True)
class SupplierPaymentResult:
    completed: bool
    payment_id: int | None
    payment_status: str | None
    posted_journal_entry_id: int | None
    wizard_run_id: int | None


class SupplierPaymentWizard:
    @staticmethod
    def steps_factory():
        return [HeaderStep(), AllocateStep(), ConfirmStep()]

    @staticmethod
    def advisor_factory():
        return build_supplier_payment_advisor()


def launch_supplier_payment_wizard(
    service_registry: ServiceRegistry,
    *,
    parent: QWidget | None = None,
) -> SupplierPaymentResult:
    outcome = launch_wizard(
        service_registry=service_registry,
        wizard_code=WIZARD_CODE,
        title="Supplier Payment",
        intro=(
            "Capture an AP payment, allocate it across open bills, and "
            "optionally post it to the GL in one flow."
        ),
        steps_factory=SupplierPaymentWizard.steps_factory,
        advisor_factory=SupplierPaymentWizard.advisor_factory,
        feature_label="Supplier Payment",
        parent=parent,
    )
    if outcome is None:
        return SupplierPaymentResult(False, None, None, None, None)
    assert isinstance(outcome, WizardOutcome)
    pid = outcome.state.get(K.KEY_PAYMENT_ID)
    je = outcome.state.get(K.KEY_POSTED_JOURNAL_ENTRY_ID)
    return SupplierPaymentResult(
        completed=outcome.completed,
        payment_id=int(pid) if isinstance(pid, int) else None,
        payment_status=outcome.state.get(K.KEY_PAYMENT_STATUS),
        posted_journal_entry_id=int(je) if isinstance(je, int) else None,
        wizard_run_id=outcome.wizard_run_id,
    )
