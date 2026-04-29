"""Offscreen smoke for W9-W16 wizards.

Builds each wizard's host dialog with a MagicMock'd ServiceRegistry and renders
the first step. No service commits run.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from seeker_accounting.modules.wizards.bank_cash_setup import BankCashSetupWizard  # noqa: E402
from seeker_accounting.modules.wizards.document_numbering import DocumentNumberingWizard  # noqa: E402
from seeker_accounting.modules.wizards.new_item import NewItemWizard  # noqa: E402
from seeker_accounting.modules.wizards.new_supplier import NewSupplierWizard  # noqa: E402
from seeker_accounting.modules.wizards.opening_balances import OpeningBalancesWizard  # noqa: E402
from seeker_accounting.modules.wizards.purchase_credit_note import PurchaseCreditNoteWizard  # noqa: E402
from seeker_accounting.modules.wizards.sales_credit_note import SalesCreditNoteWizard  # noqa: E402
from seeker_accounting.modules.wizards.user_provisioning import UserProvisioningWizard  # noqa: E402
from seeker_accounting.platform.wizards import (  # noqa: E402
    AssistantEngine,
    WizardContext,
    WizardController,
    WizardState,
)
from seeker_accounting.platform.wizards.host_dialog import WizardHostDialog  # noqa: E402


def _registry() -> MagicMock:
    sr = MagicMock()
    # Customers / suppliers
    sr.customer_service.list_customers.return_value = []
    sr.customer_service.list_customer_groups.return_value = []
    sr.supplier_service.list_suppliers.return_value = []
    sr.supplier_service.list_supplier_groups.return_value = []
    # Reference / accounts / tax
    sr.reference_data_service.list_payment_terms.return_value = []
    sr.chart_of_accounts_service.list_accounts.return_value = []
    sr.tax_setup_service.list_tax_codes.return_value = []
    # Inventory reference
    sr.unit_of_measure_service.list_units_of_measure.return_value = []
    sr.item_category_service.list_item_categories.return_value = []
    # Sales / invoices
    sr.sales_invoice_service.list_open_invoices_for_customer.return_value = []
    # Purchases / bills
    sr.purchase_bill_service.list_open_bills_for_supplier.return_value = []
    # Reference data — currencies for bank/cash setup
    sr.reference_data_service.list_active_currencies.return_value = []
    # Administration — roles for user provisioning
    sr.user_auth_service.list_roles.return_value = []
    # Numbering
    sr.numbering_setup_service.list_document_sequences.return_value = []
    sr.numbering_setup_service.get_document_sequence.return_value = SimpleNamespace(
        id=1,
        company_id=1,
        document_type_code="sales_invoice",
        prefix="INV-",
        suffix=None,
        next_number=1,
        padding_width=4,
        reset_frequency_code=None,
        is_active=True,
    )
    sr.numbering_setup_service.preview_document_number.return_value = SimpleNamespace(
        company_id=1, sequence_id=1, document_type_code="sales_invoice",
        next_number=1, preview_number="INV-0001",
    )
    # Bank reconciliation summary stub (unused here but harmless)
    sr.bank_reconciliation_service.get_reconciliation_summary.return_value = SimpleNamespace(
        total_matched_amount=Decimal("0"),
        unmatched_statement_count=0,
        matched_statement_count=0,
    )
    return sr


def _build(wizard_code: str, steps, advisor) -> WizardHostDialog:
    sr = _registry()
    ctx = WizardContext(service_registry=sr, company_id=1, user_id=1, wizard_run_id=None)
    controller = WizardController(
        wizard_code=wizard_code,
        steps=steps,
        context=ctx,
        state=WizardState(),
        advisor=advisor,
        assistant_engine=AssistantEngine(),
    )
    dialog = WizardHostDialog(controller=controller, title=wizard_code, intro="smoke")
    dialog.show()
    return dialog


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    cases = [
        ("new_supplier", NewSupplierWizard),
        ("new_item", NewItemWizard),
        ("sales_credit_note", SalesCreditNoteWizard),
        ("document_numbering", DocumentNumberingWizard),
        ("opening_balances", OpeningBalancesWizard),
        ("purchase_credit_note", PurchaseCreditNoteWizard),
        ("bank_cash_setup", BankCashSetupWizard),
        ("user_provisioning", UserProvisioningWizard),
    ]
    for code, cls in cases:
        d = _build(code, cls.steps_factory(), cls.advisor_factory())
        app.processEvents()
        d.close()
        print(f"  rendered {code}")
    print("OK W9-W16 wizard smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
