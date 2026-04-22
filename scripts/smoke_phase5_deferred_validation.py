"""smoke_phase5_deferred_validation.py

Validates Phase 5 deferred items:
  - Receipts tab on SalesInvoiceDetailPage
  - Payments tab on PurchaseBillDetailPage

Run:
    $env:QT_QPA_PLATFORM="offscreen"
    python scripts/smoke_phase5_deferred_validation.py
"""
from __future__ import annotations

import os
import sys

# ── Workspace root on path ────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

errors: list[str] = []


def check(label: str, fn) -> None:
    try:
        fn()
        print(f"  [OK] {label}")
    except Exception as exc:
        errors.append(f"FAIL — {label}: {exc}")
        print(f"  [FAIL] {label}: {exc}")


# ── 1. DTO availability ────────────────────────────────────────────────────────
def _check_dtos() -> None:
    from seeker_accounting.modules.sales.dto.customer_receipt_dto import InvoiceReceiptRowDTO  # noqa: F401
    from seeker_accounting.modules.purchases.dto.supplier_payment_dto import BillPaymentRowDTO  # noqa: F401


check("InvoiceReceiptRowDTO importable", _check_dtos)


def _check_bill_dto() -> None:
    from seeker_accounting.modules.purchases.dto.supplier_payment_dto import BillPaymentRowDTO  # noqa: F401


check("BillPaymentRowDTO importable", _check_bill_dto)

# ── 2. Service method existence ───────────────────────────────────────────────
def _check_receipt_service_method() -> None:
    from seeker_accounting.modules.sales.services.customer_receipt_service import CustomerReceiptService
    assert hasattr(CustomerReceiptService, "list_receipts_for_invoice"), \
        "list_receipts_for_invoice missing on CustomerReceiptService"


def _check_payment_service_method() -> None:
    from seeker_accounting.modules.purchases.services.supplier_payment_service import SupplierPaymentService
    assert hasattr(SupplierPaymentService, "list_payments_for_bill"), \
        "list_payments_for_bill missing on SupplierPaymentService"


check("CustomerReceiptService.list_receipts_for_invoice exists", _check_receipt_service_method)
check("SupplierPaymentService.list_payments_for_bill exists", _check_payment_service_method)

# ── 3. UI page construction ────────────────────────────────────────────────────
from PySide6.QtWidgets import QApplication  # noqa: E402
_app = QApplication.instance() or QApplication(sys.argv)


def _check_sales_invoice_detail_page() -> None:
    from seeker_accounting.modules.sales.ui.sales_invoice_detail_page import SalesInvoiceDetailPage


def _check_purchase_bill_detail_page() -> None:
    from seeker_accounting.modules.purchases.ui.purchase_bill_detail_page import PurchaseBillDetailPage


check("SalesInvoiceDetailPage imports cleanly", _check_sales_invoice_detail_page)
check("PurchaseBillDetailPage imports cleanly", _check_purchase_bill_detail_page)

# ── 4. Tab counts ─────────────────────────────────────────────────────────────
def _check_sales_invoice_tab_count() -> None:
    from seeker_accounting.modules.sales.ui.sales_invoice_detail_page import SalesInvoiceDetailPage
    tab_method = SalesInvoiceDetailPage._build_tabs
    # Inspect method to ensure it returns 3 entries by examining the source
    import inspect
    src = inspect.getsource(tab_method)
    assert src.count('("Lines"') >= 1, "Missing Lines tab"
    assert src.count('("Receipts"') >= 1, "Missing Receipts tab"
    assert src.count('("Details"') >= 1, "Missing Details tab"


def _check_purchase_bill_tab_count() -> None:
    from seeker_accounting.modules.purchases.ui.purchase_bill_detail_page import PurchaseBillDetailPage
    import inspect
    src = inspect.getsource(PurchaseBillDetailPage._build_tabs)
    assert src.count('("Lines"') >= 1, "Missing Lines tab"
    assert src.count('("Payments"') >= 1, "Missing Payments tab"
    assert src.count('("Details"') >= 1, "Missing Details tab"


check("SalesInvoiceDetailPage has Lines/Receipts/Details tabs", _check_sales_invoice_tab_count)
check("PurchaseBillDetailPage has Lines/Payments/Details tabs", _check_purchase_bill_tab_count)

# ── 5. Builder method existence ───────────────────────────────────────────────
def _check_receipts_builder() -> None:
    from seeker_accounting.modules.sales.ui.sales_invoice_detail_page import SalesInvoiceDetailPage
    assert hasattr(SalesInvoiceDetailPage, "_build_receipts_tab"), "_build_receipts_tab missing"
    assert hasattr(SalesInvoiceDetailPage, "_populate_receipts_tab"), "_populate_receipts_tab missing"
    assert hasattr(SalesInvoiceDetailPage, "_on_receipt_double_clicked"), "_on_receipt_double_clicked missing"


def _check_payments_builder() -> None:
    from seeker_accounting.modules.purchases.ui.purchase_bill_detail_page import PurchaseBillDetailPage
    assert hasattr(PurchaseBillDetailPage, "_build_payments_tab"), "_build_payments_tab missing"
    assert hasattr(PurchaseBillDetailPage, "_populate_payments_tab"), "_populate_payments_tab missing"
    assert hasattr(PurchaseBillDetailPage, "_on_payment_double_clicked"), "_on_payment_double_clicked missing"


check("SalesInvoiceDetailPage has receipts tab builder/populator/handler", _check_receipts_builder)
check("PurchaseBillDetailPage has payments tab builder/populator/handler", _check_payments_builder)

# ── Result ────────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"=== PHASE 5 DEFERRED VALIDATION: FAILED ({len(errors)} error(s)) ===")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("=== PHASE 5 DEFERRED VALIDATION: PASSED ===")
    sys.exit(0)
