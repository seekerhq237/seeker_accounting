"""Receipt Allocation Wizard \u2014 capture a customer receipt and allocate to open invoices."""
from seeker_accounting.modules.wizards.receipt_allocation.wizard import (
    ReceiptAllocationResult,
    ReceiptAllocationWizard,
    launch_receipt_allocation_wizard,
)

__all__ = [
    "ReceiptAllocationResult",
    "ReceiptAllocationWizard",
    "launch_receipt_allocation_wizard",
]
