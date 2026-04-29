"""Offscreen smoke for W3-W8 wizards.

Builds each wizard's host dialog with a MagicMock'd ServiceRegistry and renders
the first step. No service commits run.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from seeker_accounting.modules.wizards.bank_reconciliation import BankReconciliationWizard
from seeker_accounting.modules.wizards.depreciation_run import DepreciationRunWizard
from seeker_accounting.modules.wizards.new_customer import NewCustomerWizard
from seeker_accounting.modules.wizards.period_reopen import PeriodReopenWizard
from seeker_accounting.modules.wizards.receipt_allocation import ReceiptAllocationWizard
from seeker_accounting.modules.wizards.supplier_payment import SupplierPaymentWizard
from seeker_accounting.platform.wizards import (
    AssistantEngine,
    WizardContext,
    WizardController,
    WizardState,
)
from seeker_accounting.platform.wizards.host_dialog import WizardHostDialog


def _registry() -> MagicMock:
    sr = MagicMock()
    sr.fiscal_calendar_service.list_periods.return_value = []
    sr.depreciation_run_service.list_depreciation_runs.return_value = []
    sr.financial_account_service.list_financial_accounts.return_value = []
    sr.customer_service.list_customers.return_value = []
    sr.customer_service.list_customer_groups.return_value = []
    sr.supplier_service.list_suppliers.return_value = []
    sr.sales_invoice_service.list_open_invoices_for_customer.return_value = []
    sr.purchase_bill_service.list_open_bills_for_supplier.return_value = []
    sr.reference_data_service.list_payment_terms.return_value = []
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
        ("period_reopen", PeriodReopenWizard),
        ("depreciation_run", DepreciationRunWizard),
        ("bank_reconciliation", BankReconciliationWizard),
        ("receipt_allocation", ReceiptAllocationWizard),
        ("supplier_payment", SupplierPaymentWizard),
        ("new_customer", NewCustomerWizard),
    ]
    for code, cls in cases:
        d = _build(code, cls.steps_factory(), cls.advisor_factory())
        app.processEvents()
        d.close()
        print(f"  rendered {code}")
    print("OK W3-W8 wizard smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
