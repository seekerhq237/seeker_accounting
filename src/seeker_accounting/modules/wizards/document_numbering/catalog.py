"""Catalog of valid document type codes (mirrors numbering_setup_service)."""
from __future__ import annotations

VALID_DOCUMENT_TYPES: tuple[tuple[str, str], ...] = (
    ("sales_invoice", "Sales Invoice"),
    ("customer_receipt", "Customer Receipt"),
    ("purchase_bill", "Purchase Bill"),
    ("supplier_payment", "Supplier Payment"),
    ("treasury_transaction", "Treasury Transaction"),
    ("journal_entry", "Journal Entry"),
    ("inventory_document", "Inventory Document"),
    ("asset", "Fixed Asset"),
    ("depreciation_run", "Depreciation Run"),
    ("payroll_run", "Payroll Run"),
    ("payroll_input_batch", "Payroll Input Batch"),
    ("payroll_remittance", "Payroll Remittance"),
    ("contract", "Contract"),
    ("contract_change_order", "Contract Change Order"),
    ("project", "Project"),
    ("project_commitment", "Project Commitment"),
    ("project_budget_version", "Project Budget Version"),
)

RESET_FREQUENCY_OPTIONS: tuple[tuple[str | None, str], ...] = (
    (None, "Never"),
    ("MONTHLY", "Monthly"),
    ("YEARLY", "Yearly"),
)
