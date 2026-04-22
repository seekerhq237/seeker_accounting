"""Insert _record_audit calls after commits in service mutation methods.

Each entry specifies:
  file, method_name, event_code_constant, entity_type, entity_id_expr, company_id_expr, description

Strategy: For each method, find the LAST `uow.commit()` call, then find the
next `return` statement within the same method, and insert the audit call
just before that return.  If there is no return (e.g., deactivate methods
that return None), insert right after the commit or try/except block.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "seeker_accounting"

# (file, method, event_const, entity_type, id_expr, company_id_expr, desc)
# company_id_expr: usually "company_id", but for create_company it's "company.id"
AUDIT_CALLS: list[tuple[Path, str, str, str, str, str, str]] = [
    # ── Customers ──
    (ROOT / "modules/customers/services/customer_service.py",
     "create_customer_group", "CUSTOMER_GROUP_CREATED", "CustomerGroup", "group.id",
     "company_id", 'f"Created customer group {group.code}"'),
    (ROOT / "modules/customers/services/customer_service.py",
     "update_customer_group", "CUSTOMER_GROUP_UPDATED", "CustomerGroup", "group.id",
     "company_id", 'f"Updated customer group {group.code}"'),
    (ROOT / "modules/customers/services/customer_service.py",
     "deactivate_customer_group", "CUSTOMER_GROUP_DEACTIVATED", "CustomerGroup", "group.id",
     "company_id", '"Deactivated customer group"'),
    (ROOT / "modules/customers/services/customer_service.py",
     "create_customer", "CUSTOMER_CREATED", "Customer", "customer.id",
     "company_id", 'f"Created customer"'),
    (ROOT / "modules/customers/services/customer_service.py",
     "update_customer", "CUSTOMER_UPDATED", "Customer", "customer.id",
     "company_id", '"Updated customer"'),
    (ROOT / "modules/customers/services/customer_service.py",
     "deactivate_customer", "CUSTOMER_DEACTIVATED", "Customer", "customer_id",
     "company_id", '"Deactivated customer"'),

    # ── Suppliers ──
    (ROOT / "modules/suppliers/services/supplier_service.py",
     "create_supplier_group", "SUPPLIER_GROUP_CREATED", "SupplierGroup", "group.id",
     "company_id", 'f"Created supplier group {group.code}"'),
    (ROOT / "modules/suppliers/services/supplier_service.py",
     "update_supplier_group", "SUPPLIER_GROUP_UPDATED", "SupplierGroup", "group.id",
     "company_id", 'f"Updated supplier group {group.code}"'),
    (ROOT / "modules/suppliers/services/supplier_service.py",
     "deactivate_supplier_group", "SUPPLIER_GROUP_DEACTIVATED", "SupplierGroup", "group.id",
     "company_id", '"Deactivated supplier group"'),
    (ROOT / "modules/suppliers/services/supplier_service.py",
     "create_supplier", "SUPPLIER_CREATED", "Supplier", "supplier.id",
     "company_id", '"Created supplier"'),
    (ROOT / "modules/suppliers/services/supplier_service.py",
     "update_supplier", "SUPPLIER_UPDATED", "Supplier", "supplier.id",
     "company_id", '"Updated supplier"'),
    (ROOT / "modules/suppliers/services/supplier_service.py",
     "deactivate_supplier", "SUPPLIER_DEACTIVATED", "Supplier", "supplier_id",
     "company_id", '"Deactivated supplier"'),

    # ── Sales ──
    (ROOT / "modules/sales/services/sales_invoice_service.py",
     "create_draft_invoice", "SALES_INVOICE_CREATED", "SalesInvoice", "invoice.id",
     "company_id", '"Created sales invoice"'),
    (ROOT / "modules/sales/services/sales_invoice_service.py",
     "update_draft_invoice", "SALES_INVOICE_UPDATED", "SalesInvoice", "invoice.id",
     "company_id", '"Updated sales invoice"'),
    (ROOT / "modules/sales/services/sales_invoice_posting_service.py",
     "post_invoice", "SALES_INVOICE_POSTED", "SalesInvoice", "invoice.id",
     "company_id", '"Posted sales invoice"'),
    (ROOT / "modules/sales/services/customer_receipt_service.py",
     "create_draft_receipt", "CUSTOMER_RECEIPT_CREATED", "CustomerReceipt", "receipt.id",
     "company_id", '"Created customer receipt"'),
    (ROOT / "modules/sales/services/customer_receipt_service.py",
     "update_draft_receipt", "CUSTOMER_RECEIPT_UPDATED", "CustomerReceipt", "receipt.id",
     "company_id", '"Updated customer receipt"'),
    (ROOT / "modules/sales/services/customer_receipt_posting_service.py",
     "post_receipt", "CUSTOMER_RECEIPT_POSTED", "CustomerReceipt", "receipt.id",
     "company_id", '"Posted customer receipt"'),

    # ── Purchases ──
    (ROOT / "modules/purchases/services/purchase_bill_service.py",
     "create_draft_bill", "PURCHASE_BILL_CREATED", "PurchaseBill", "bill.id",
     "company_id", '"Created purchase bill"'),
    (ROOT / "modules/purchases/services/purchase_bill_service.py",
     "update_draft_bill", "PURCHASE_BILL_UPDATED", "PurchaseBill", "bill.id",
     "company_id", '"Updated purchase bill"'),
    (ROOT / "modules/purchases/services/purchase_bill_posting_service.py",
     "post_bill", "PURCHASE_BILL_POSTED", "PurchaseBill", "bill.id",
     "company_id", '"Posted purchase bill"'),
    (ROOT / "modules/purchases/services/supplier_payment_service.py",
     "create_draft_payment", "SUPPLIER_PAYMENT_CREATED", "SupplierPayment", "payment.id",
     "company_id", '"Created supplier payment"'),
    (ROOT / "modules/purchases/services/supplier_payment_service.py",
     "update_draft_payment", "SUPPLIER_PAYMENT_UPDATED", "SupplierPayment", "payment.id",
     "company_id", '"Updated supplier payment"'),
    (ROOT / "modules/purchases/services/supplier_payment_posting_service.py",
     "post_payment", "SUPPLIER_PAYMENT_POSTED", "SupplierPayment", "payment.id",
     "company_id", '"Posted supplier payment"'),

    # ── Treasury ──
    (ROOT / "modules/treasury/services/financial_account_service.py",
     "create_financial_account", "FINANCIAL_ACCOUNT_CREATED", "FinancialAccount", "financial_account.id",
     "company_id", '"Created financial account"'),
    (ROOT / "modules/treasury/services/financial_account_service.py",
     "update_financial_account", "FINANCIAL_ACCOUNT_UPDATED", "FinancialAccount", "financial_account.id",
     "company_id", '"Updated financial account"'),
    (ROOT / "modules/treasury/services/treasury_transaction_service.py",
     "create_draft_transaction", "TREASURY_TRANSACTION_CREATED", "TreasuryTransaction", "txn.id",
     "company_id", '"Created treasury transaction"'),
    (ROOT / "modules/treasury/services/treasury_transaction_service.py",
     "update_draft_transaction", "TREASURY_TRANSACTION_UPDATED", "TreasuryTransaction", "txn.id",
     "company_id", '"Updated treasury transaction"'),
    (ROOT / "modules/treasury/services/treasury_transaction_posting_service.py",
     "post_transaction", "TREASURY_TRANSACTION_POSTED", "TreasuryTransaction", "txn.id",
     "company_id", '"Posted treasury transaction"'),
    (ROOT / "modules/treasury/services/treasury_transfer_service.py",
     "create_draft_transfer", "TREASURY_TRANSFER_CREATED", "TreasuryTransfer", "transfer.id",
     "company_id", '"Created treasury transfer"'),
    (ROOT / "modules/treasury/services/treasury_transfer_service.py",
     "update_draft_transfer", "TREASURY_TRANSFER_UPDATED", "TreasuryTransfer", "transfer.id",
     "company_id", '"Updated treasury transfer"'),
    (ROOT / "modules/treasury/services/treasury_transfer_posting_service.py",
     "post_transfer", "TREASURY_TRANSFER_POSTED", "TreasuryTransfer", "transfer.id",
     "company_id", '"Posted treasury transfer"'),
    (ROOT / "modules/treasury/services/bank_reconciliation_service.py",
     "create_reconciliation_session", "BANK_RECONCILIATION_SESSION_CREATED", "BankReconciliationSession", "recon_session.id",
     "company_id", '"Created bank reconciliation session"'),
    (ROOT / "modules/treasury/services/bank_reconciliation_service.py",
     "complete_session", "BANK_RECONCILIATION_SESSION_COMPLETED", "BankReconciliationSession", "recon_session.id",
     "company_id", '"Completed bank reconciliation session"'),

    # ── Inventory ──
    (ROOT / "modules/inventory/services/item_service.py",
     "create_item", "ITEM_CREATED", "Item", "item.id",
     "company_id", '"Created inventory item"'),
    (ROOT / "modules/inventory/services/item_service.py",
     "update_item", "ITEM_UPDATED", "Item", "item.id",
     "company_id", '"Updated inventory item"'),
    (ROOT / "modules/inventory/services/item_category_service.py",
     "create_item_category", "ITEM_CATEGORY_CREATED", "ItemCategory", "cat.id",
     "company_id", '"Created item category"'),
    (ROOT / "modules/inventory/services/item_category_service.py",
     "update_item_category", "ITEM_CATEGORY_UPDATED", "ItemCategory", "cat.id",
     "company_id", '"Updated item category"'),
    (ROOT / "modules/inventory/services/unit_of_measure_service.py",
     "create_unit_of_measure", "UNIT_OF_MEASURE_CREATED", "UnitOfMeasure", "uom.id",
     "company_id", '"Created unit of measure"'),
    (ROOT / "modules/inventory/services/unit_of_measure_service.py",
     "update_unit_of_measure", "UNIT_OF_MEASURE_UPDATED", "UnitOfMeasure", "uom.id",
     "company_id", '"Updated unit of measure"'),
    (ROOT / "modules/inventory/services/inventory_location_service.py",
     "create_inventory_location", "INVENTORY_LOCATION_CREATED", "InventoryLocation", "loc.id",
     "company_id", '"Created inventory location"'),
    (ROOT / "modules/inventory/services/inventory_location_service.py",
     "update_inventory_location", "INVENTORY_LOCATION_UPDATED", "InventoryLocation", "loc.id",
     "company_id", '"Updated inventory location"'),
    (ROOT / "modules/inventory/services/inventory_document_service.py",
     "create_draft_document", "INVENTORY_DOCUMENT_CREATED", "InventoryDocument", "doc.id",
     "company_id", '"Created inventory document"'),
    (ROOT / "modules/inventory/services/inventory_document_service.py",
     "update_draft_document", "INVENTORY_DOCUMENT_UPDATED", "InventoryDocument", "doc.id",
     "company_id", '"Updated inventory document"'),
    (ROOT / "modules/inventory/services/inventory_posting_service.py",
     "post_inventory_document", "INVENTORY_DOCUMENT_POSTED", "InventoryDocument", "doc.id",
     "company_id", '"Posted inventory document"'),

    # ── Fixed Assets ──
    (ROOT / "modules/fixed_assets/services/asset_service.py",
     "create_asset", "ASSET_CREATED", "Asset", "asset.id",
     "company_id", '"Created fixed asset"'),
    (ROOT / "modules/fixed_assets/services/asset_service.py",
     "update_asset", "ASSET_UPDATED", "Asset", "asset.id",
     "company_id", '"Updated fixed asset"'),
    (ROOT / "modules/fixed_assets/services/asset_category_service.py",
     "create_asset_category", "ASSET_CATEGORY_CREATED", "AssetCategory", "cat.id",
     "company_id", '"Created asset category"'),
    (ROOT / "modules/fixed_assets/services/asset_category_service.py",
     "update_asset_category", "ASSET_CATEGORY_UPDATED", "AssetCategory", "cat.id",
     "company_id", '"Updated asset category"'),
    (ROOT / "modules/fixed_assets/services/depreciation_run_service.py",
     "create_run", "DEPRECIATION_RUN_CREATED", "AssetDepreciationRun", "run.id",
     "company_id", '"Created depreciation run"'),
    (ROOT / "modules/fixed_assets/services/depreciation_posting_service.py",
     "post_run", "DEPRECIATION_RUN_POSTED", "AssetDepreciationRun", "run.id",
     "company_id", '"Posted depreciation run"'),

    # ── Companies ──
    (ROOT / "modules/companies/services/company_service.py",
     "create_company", "COMPANY_CREATED", "Company", "company.id",
     "company.id", '"Created company"'),
    (ROOT / "modules/companies/services/company_service.py",
     "update_company", "COMPANY_UPDATED", "Company", "company.id",
     "company_id", '"Updated company"'),

    # ── Reference Data ──
    (ROOT / "modules/accounting/reference_data/services/reference_data_service.py",
     "create_payment_term", "PAYMENT_TERM_CREATED", "PaymentTerm", "payment_term.id",
     "company_id", '"Created payment term"'),
    (ROOT / "modules/accounting/reference_data/services/reference_data_service.py",
     "update_payment_term", "PAYMENT_TERM_UPDATED", "PaymentTerm", "payment_term.id",
     "company_id", '"Updated payment term"'),
    (ROOT / "modules/accounting/reference_data/services/tax_setup_service.py",
     "create_tax_code", "TAX_CODE_CREATED", "TaxCode", "tax_code.id",
     "company_id", '"Created tax code"'),
    (ROOT / "modules/accounting/reference_data/services/tax_setup_service.py",
     "update_tax_code", "TAX_CODE_UPDATED", "TaxCode", "tax_code.id",
     "company_id", '"Updated tax code"'),

    # ── Contracts/Projects ──
    (ROOT / "modules/contracts_projects/services/contract_service.py",
     "create_contract", "CONTRACT_CREATED", "Contract", "contract.id",
     "company_id", '"Created contract"'),
    (ROOT / "modules/contracts_projects/services/contract_service.py",
     "update_contract", "CONTRACT_UPDATED", "Contract", "contract.id",
     "company_id", '"Updated contract"'),
    (ROOT / "modules/contracts_projects/services/project_service.py",
     "create_project", "PROJECT_CREATED", "Project", "project.id",
     "company_id", '"Created project"'),
    (ROOT / "modules/contracts_projects/services/project_service.py",
     "update_project", "PROJECT_UPDATED", "Project", "project.id",
     "company_id", '"Updated project"'),

    # ── Budgeting ──
    (ROOT / "modules/budgeting/services/budget_approval_service.py",
     "approve_version", "BUDGET_VERSION_APPROVED", "ProjectBudgetVersion", "version.id",
     "company_id", '"Approved budget version"'),
    (ROOT / "modules/budgeting/services/project_budget_service.py",
     "create_version", "BUDGET_VERSION_CREATED", "ProjectBudgetVersion", "version.id",
     "company_id", '"Created budget version"'),
    (ROOT / "modules/budgeting/services/project_budget_service.py",
     "update_version", "BUDGET_VERSION_UPDATED", "ProjectBudgetVersion", "version.id",
     "company_id", '"Updated budget version"'),
]


def find_method_range(lines: list[str], method_name: str) -> tuple[int, int] | None:
    """Return (start_line, end_line) of a method, or None if not found."""
    start = None
    indent = 0
    for i, line in enumerate(lines):
        if re.search(rf"\bdef {re.escape(method_name)}\b\s*\(", line):
            start = i
            indent = len(line) - len(line.lstrip())
            continue
        if start is not None and i > start:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("\"\"\""):
                cur_indent = len(line) - len(line.lstrip())
                if cur_indent <= indent and stripped.startswith("def "):
                    return (start, i - 1)
    if start is not None:
        return (start, len(lines) - 1)
    return None


def find_last_commit_line(lines: list[str], start: int, end: int) -> int | None:
    """Find the line index of the last uow.commit() within the method range."""
    last = None
    for i in range(start, end + 1):
        if "uow.commit()" in lines[i]:
            last = i
    return last


def find_return_after(lines: list[str], after: int, end: int) -> int | None:
    """Find the first 'return' statement after a given line within method range."""
    for i in range(after + 1, end + 1):
        stripped = lines[i].strip()
        if stripped.startswith("return ") or stripped == "return":
            return i
    return None


def find_insert_point_after_commit(lines: list[str], commit_line: int, end: int) -> tuple[int, str]:
    """Find where to insert the audit call after commit and determine indentation.
    
    Returns (insert_line_index, indent_string).
    
    Strategy:
    1. If there's a try/except wrapping the commit, find the end of the except block
    2. Then look for the next return statement
    3. Insert just before the return, or after the try/except block
    """
    commit_indent = len(lines[commit_line]) - len(lines[commit_line].lstrip())
    
    # Check if commit is inside a try block by looking upward
    in_try = False
    try_indent = 0
    for i in range(commit_line - 1, max(commit_line - 10, 0), -1):
        stripped = lines[i].strip()
        if stripped == "try:":
            in_try = True
            try_indent = len(lines[i]) - len(lines[i].lstrip())
            break
        elif stripped and not stripped.startswith("#"):
            # Check if this line's indent is less than or equal to commit indent
            line_indent = len(lines[i]) - len(lines[i].lstrip())
            if line_indent < commit_indent and not stripped.startswith("try:"):
                break
    
    if in_try:
        # Find the matching except block and its end
        except_end = None
        for i in range(commit_line + 1, end + 1):
            stripped = lines[i].strip()
            if not stripped or stripped.startswith("#"):
                continue
            line_indent = len(lines[i]) - len(lines[i].lstrip())
            if line_indent == try_indent and stripped.startswith("except "):
                # Found the except, now find its end
                for j in range(i + 1, end + 1):
                    s2 = lines[j].strip()
                    if not s2 or s2.startswith("#"):
                        continue
                    j_indent = len(lines[j]) - len(lines[j].lstrip())
                    if j_indent <= try_indent:
                        except_end = j
                        break
                if except_end is None:
                    except_end = end + 1
                break
            elif line_indent <= try_indent:
                # No except block found
                except_end = i
                break
        
        if except_end is not None:
            # Insert at except_end position, with indent matching the try block
            # Look for a return at or after except_end
            ret = find_return_after(lines, except_end - 2, end)
            if ret is not None:
                indent = " " * (len(lines[ret]) - len(lines[ret].lstrip()))
                return (ret, indent)
            return (except_end, " " * try_indent)
    
    # No try/except — look for return after commit
    ret = find_return_after(lines, commit_line, end)
    if ret is not None:
        indent = " " * (len(lines[ret]) - len(lines[ret].lstrip()))
        return (ret, indent)
    
    # No return found — insert right after commit line
    return (commit_line + 1, " " * commit_indent)


def insert_audit_call(
    filepath: Path,
    method_name: str,
    event_const: str,
    entity_type: str,
    id_expr: str,
    company_id_expr: str,
    desc: str,
) -> bool:
    """Insert a _record_audit call into a method after its last commit.
    
    Returns True if the file was modified.
    """
    if not filepath.exists():
        print(f"  WARN: File not found: {filepath}")
        return False
    
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    method_range = find_method_range(lines, method_name)
    if method_range is None:
        print(f"  WARN: Method {method_name} not found in {filepath.name}")
        return False
    
    start, end = method_range
    
    # Check if already instrumented
    for i in range(start, end + 1):
        if "_record_audit(" in lines[i]:
            return False  # Already has audit call
    
    # Find the last commit
    commit_line = find_last_commit_line(lines, start, end)
    if commit_line is None:
        print(f"  WARN: No uow.commit() found in {method_name} of {filepath.name}")
        return False
    
    # Find insertion point
    insert_at, indent = find_insert_point_after_commit(lines, commit_line, end)
    
    # Build the audit call lines
    audit_lines = [
        f"{indent}from seeker_accounting.modules.audit.event_type_catalog import {event_const}",
        f"{indent}self._record_audit({company_id_expr}, {event_const}, \"{entity_type}\", {id_expr}, {desc})",
    ]
    
    # Insert
    for j, al in enumerate(audit_lines):
        lines.insert(insert_at + j, al)
    
    filepath.write_text("\n".join(lines), encoding="utf-8")
    return True


def main() -> None:
    from collections import defaultdict
    by_file: dict[Path, list] = defaultdict(list)
    for entry in AUDIT_CALLS:
        by_file[entry[0]].append(entry[1:])
    
    total_inserted = 0
    total_skipped = 0
    total_warned = 0
    
    for filepath, methods in sorted(by_file.items()):
        for method_name, event_const, entity_type, id_expr, company_id_expr, desc in methods:
            # Re-read file each time since previous inserts shift line numbers
            result = insert_audit_call(filepath, method_name, event_const, entity_type, id_expr, company_id_expr, desc)
            if result:
                total_inserted += 1
                print(f"  + {filepath.name}:{method_name} -> {event_const}")
            else:
                # Check if it was skipped (already done) or warned
                if filepath.exists():
                    content = filepath.read_text(encoding="utf-8")
                    lines = content.split("\n")
                    mr = find_method_range(lines, method_name)
                    if mr and any("_record_audit(" in lines[i] for i in range(mr[0], mr[1]+1)):
                        total_skipped += 1
                    else:
                        total_warned += 1
                else:
                    total_warned += 1
    
    print(f"\n=== Audit Call Insertion ===")
    print(f"Inserted: {total_inserted}")
    print(f"Skipped (already done): {total_skipped}")
    print(f"Warnings: {total_warned}")


if __name__ == "__main__":
    main()
