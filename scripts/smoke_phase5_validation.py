"""Phase 5 validation smoke script.

Tests:
- nav_ids additions
- shell_models PLACEHOLDER_PAGES entries
- workspace_host factory entries
- SalesInvoiceDetailPage import chain
- PurchaseBillDetailPage import chain
- Widget construction (offscreen Qt)

Run: $env:QT_QPA_PLATFORM="offscreen"; python scripts/smoke_phase5_validation.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

_PASS = []
_FAIL = []


def check(name: str, fn):
    try:
        fn()
        _PASS.append(name)
        print(f"  PASS  {name}")
    except Exception as exc:
        _FAIL.append((name, exc))
        print(f"  FAIL  {name}: {exc}")


# ── 1. nav_ids additions ──────────────────────────────────────────────

def _check_nav_ids():
    from seeker_accounting.app.navigation import nav_ids
    assert hasattr(nav_ids, "SALES_INVOICE_DETAIL"), "SALES_INVOICE_DETAIL missing"
    assert hasattr(nav_ids, "PURCHASE_BILL_DETAIL"), "PURCHASE_BILL_DETAIL missing"
    assert nav_ids.SALES_INVOICE_DETAIL == "sales_invoice_detail"
    assert nav_ids.PURCHASE_BILL_DETAIL == "purchase_bill_detail"
    assert "sales_invoice_detail" in nav_ids.ALL_NAV_IDS
    assert "purchase_bill_detail" in nav_ids.ALL_NAV_IDS

check("nav_ids.SALES_INVOICE_DETAIL + PURCHASE_BILL_DETAIL present", _check_nav_ids)

# ── 2. shell_models PLACEHOLDER_PAGES entries ─────────────────────────

def _check_shell_models():
    from seeker_accounting.app.navigation import nav_ids
    from seeker_accounting.app.shell.shell_models import PLACEHOLDER_PAGES
    assert nav_ids.SALES_INVOICE_DETAIL in PLACEHOLDER_PAGES, "SALES_INVOICE_DETAIL not in PLACEHOLDER_PAGES"
    assert nav_ids.PURCHASE_BILL_DETAIL in PLACEHOLDER_PAGES, "PURCHASE_BILL_DETAIL not in PLACEHOLDER_PAGES"
    inv_model = PLACEHOLDER_PAGES[nav_ids.SALES_INVOICE_DETAIL]
    bill_model = PLACEHOLDER_PAGES[nav_ids.PURCHASE_BILL_DETAIL]
    assert inv_model.title == "Sales Invoice Detail"
    assert bill_model.title == "Purchase Bill Detail"

check("PLACEHOLDER_PAGES entries", _check_shell_models)

# ── 3. Import chain — SalesInvoiceDetailPage ──────────────────────────

def _check_sales_invoice_detail_import():
    from seeker_accounting.modules.sales.ui.sales_invoice_detail_page import SalesInvoiceDetailPage
    assert SalesInvoiceDetailPage is not None

check("SalesInvoiceDetailPage import", _check_sales_invoice_detail_import)

# ── 4. Import chain — PurchaseBillDetailPage ──────────────────────────

def _check_purchase_bill_detail_import():
    from seeker_accounting.modules.purchases.ui.purchase_bill_detail_page import PurchaseBillDetailPage
    assert PurchaseBillDetailPage is not None

check("PurchaseBillDetailPage import", _check_purchase_bill_detail_import)

# ── 5. Qt widget construction (offscreen) ─────────────────────────────

def _check_widget_construction():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    # Build a mock service_registry that is safe to pass (pages don't call services in __init__)
    class _FakeSR:
        def __getattr__(self, name):
            raise AttributeError(f"FakeSR has no attribute {name!r}")

    from seeker_accounting.modules.sales.ui.sales_invoice_detail_page import SalesInvoiceDetailPage
    inv_page = SalesInvoiceDetailPage(_FakeSR())  # type: ignore[arg-type]
    assert inv_page is not None
    assert inv_page.objectName() == "SalesInvoiceDetailPage"

    from seeker_accounting.modules.purchases.ui.purchase_bill_detail_page import PurchaseBillDetailPage
    bill_page = PurchaseBillDetailPage(_FakeSR())  # type: ignore[arg-type]
    assert bill_page is not None
    assert bill_page.objectName() == "PurchaseBillDetailPage"

check("Qt widget construction (offscreen)", _check_widget_construction)

# ── 6. workspace_host factory entries ─────────────────────────────────

def _check_workspace_host_factory():
    import ast, pathlib
    src = pathlib.Path(__file__).parent.parent / "src/seeker_accounting/app/shell/workspace_host.py"
    text = src.read_text(encoding="utf-8")
    assert "SALES_INVOICE_DETAIL" in text, "SALES_INVOICE_DETAIL not in workspace_host.py"
    assert "PURCHASE_BILL_DETAIL" in text, "PURCHASE_BILL_DETAIL not in workspace_host.py"
    assert "SalesInvoiceDetailPage" in text
    assert "PurchaseBillDetailPage" in text

check("workspace_host factory entries", _check_workspace_host_factory)

# ── 7. List page double-click wiring ─────────────────────────────────

def _check_list_page_wiring():
    import pathlib
    inv_src = pathlib.Path(__file__).parent.parent / "src/seeker_accounting/modules/sales/ui/sales_invoices_page.py"
    inv_text = inv_src.read_text(encoding="utf-8")
    assert "SALES_INVOICE_DETAIL" in inv_text, "SALES_INVOICE_DETAIL not in sales_invoices_page.py"
    assert "_open_edit_dialog" not in inv_text.split("_handle_item_double_clicked")[1].split("\n\n")[0], \
        "_open_edit_dialog still called from _handle_item_double_clicked"

    bill_src = pathlib.Path(__file__).parent.parent / "src/seeker_accounting/modules/purchases/ui/purchase_bills_page.py"
    bill_text = bill_src.read_text(encoding="utf-8")
    assert "PURCHASE_BILL_DETAIL" in bill_text, "PURCHASE_BILL_DETAIL not in purchase_bills_page.py"

check("List page double-click wiring", _check_list_page_wiring)

# ── Results ───────────────────────────────────────────────────────────

print()
print(f"Results: {len(_PASS)} passed, {len(_FAIL)} failed")
if _FAIL:
    print("\nFailed checks:")
    for name, exc in _FAIL:
        print(f"  {name}: {exc}")
    sys.exit(1)
else:
    print()
    print("=== PHASE 5 VALIDATION: PASSED ===")
    sys.exit(0)
