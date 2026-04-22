"""Wire audit_service through factory functions in factories.py.

Simple line-based approach: for each factory function, add audit_service
parameter to the signature and constructor call, then update the registry calls.
"""
from __future__ import annotations

from pathlib import Path

FACTORIES_PATH = Path(__file__).resolve().parent.parent / "src" / "seeker_accounting" / "app" / "dependency" / "factories.py"

# Factory functions that need audit_service wired
FACTORY_FUNCTIONS = [
    "create_customer_service",
    "create_supplier_service",
    "create_sales_invoice_service",
    "create_sales_invoice_posting_service",
    "create_customer_receipt_service",
    "create_customer_receipt_posting_service",
    "create_purchase_bill_service",
    "create_purchase_bill_posting_service",
    "create_supplier_payment_service",
    "create_supplier_payment_posting_service",
    "create_financial_account_service",
    "create_treasury_transaction_service",
    "create_treasury_transaction_posting_service",
    "create_treasury_transfer_service",
    "create_treasury_transfer_posting_service",
    "create_bank_reconciliation_service",
    "create_bank_statement_service",
    "create_item_service",
    "create_item_category_service",
    "create_unit_of_measure_service",
    "create_inventory_location_service",
    "create_inventory_document_service",
    "create_inventory_posting_service",
    "create_asset_service",
    "create_asset_category_service",
    "create_depreciation_run_service",
    "create_depreciation_posting_service",
    "create_company_service",
    "create_reference_data_service",
    "create_tax_setup_service",
    "create_contract_service",
    "create_project_service",
    "create_budget_approval_service",
    "create_project_budget_service",
    "create_user_auth_service",
    "create_journal_service",
    "create_journal_posting_service",
    "create_fiscal_calendar_service",
    "create_period_control_service",
    "create_chart_of_accounts_service",
]


def process_lines(lines: list[str]) -> list[str]:
    """Process the file lines to add audit_service wiring."""
    result = lines[:]
    
    # Step 1: Move audit_service creation up in create_service_registry
    # Find the block and move it
    registry_start = None
    for i, line in enumerate(result):
        if "def create_service_registry(" in line:
            registry_start = i
            break
    
    if registry_start is None:
        print("  ERROR: create_service_registry not found")
        return result
    
    # Find audit_service creation block
    audit_block_start = None
    audit_block_end = None
    for i in range(registry_start, len(result)):
        if "    audit_service = create_audit_service(" in result[i]:
            audit_block_start = i
            # Find end of call (closing paren with indent 4)
            for j in range(i + 1, len(result)):
                if result[j].strip() == ")":
                    audit_block_end = j
                    break
            break
    
    if audit_block_start is not None and audit_block_end is not None:
        # Extract the block
        audit_block = result[audit_block_start:audit_block_end + 1]
        # Remove from current position
        del result[audit_block_start:audit_block_end + 1]
        
        # Find permission_service creation (insert after it)
        insert_after = None
        for i in range(registry_start, len(result)):
            if "    permission_service = create_permission_service(" in result[i]:
                # Find end of this call
                if ")" in result[i]:
                    insert_after = i + 1
                else:
                    for j in range(i + 1, len(result)):
                        if result[j].strip() == ")":
                            insert_after = j + 1
                            break
                break
        
        if insert_after is not None:
            for j, line in enumerate(audit_block):
                result.insert(insert_after + j, line)
            print("  Moved audit_service creation to after permission_service")
    
    # Step 2: For each factory function, add audit_service param and constructor arg
    for func_name in FACTORY_FUNCTIONS:
        # Find function definition
        func_start = None
        for i, line in enumerate(result):
            if f"def {func_name}(" in line:
                func_start = i
                break
        
        if func_start is None:
            print(f"  WARN: {func_name} not found")
            continue
        
        # Check if already has audit_service in signature
        sig_end = None
        has_audit = False
        for i in range(func_start, min(func_start + 20, len(result))):
            if "audit_service" in result[i]:
                has_audit = True
            if result[i].strip().startswith(") ->"):
                sig_end = i
                break
        
        if has_audit:
            continue  # Already has audit_service
        
        if sig_end is not None:
            # Insert audit_service parameter before the closing ) -> line
            result.insert(sig_end, "    audit_service: AuditService | None = None,")
            print(f"  + {func_name}: added param to signature")
            
            # Now find the return constructor call's closing paren
            # It's within the same function, look for "    )" (4+4=8 space indent closing)
            func_body_start = sig_end + 2  # Skip past ): line
            for i in range(func_body_start, min(func_body_start + 40, len(result))):
                if result[i].strip() == ")" and result[i].startswith("    "):
                    # This is the closing paren of the return constructor
                    # Check it's a return statement by looking back for "return"
                    is_return = False
                    for j in range(i - 1, max(i - 30, func_body_start - 1), -1):
                        if "return " in result[j]:
                            is_return = True
                            break
                    if is_return:
                        # Check if audit_service= already in constructor
                        has_arg = False
                        for j in range(i - 1, max(i - 30, func_body_start - 1), -1):
                            if "audit_service=" in result[j]:
                                has_arg = True
                                break
                            if "return " in result[j]:
                                break
                        if not has_arg:
                            result.insert(i, "        audit_service=audit_service,")
                            print(f"  + {func_name}: added arg to constructor")
                        break
    
    # Step 3: Add audit_service=audit_service to each call in create_service_registry
    # Re-find registry start since lines shifted
    registry_start = None
    for i, line in enumerate(result):
        if "def create_service_registry(" in line:
            registry_start = i
            break
    
    if registry_start is None:
        return result
    
    for func_name in FACTORY_FUNCTIONS:
        # Find the call: "    xxx = func_name("
        call_line = None
        for i in range(registry_start, len(result)):
            stripped = result[i].strip()
            if f"= {func_name}(" in result[i] or result[i].strip() == f"{func_name}(":
                call_line = i
                break
        
        if call_line is None:
            print(f"  WARN: {func_name}() call not found in registry")
            continue
        
        # Check if it's a one-liner or multi-line call
        if result[call_line].rstrip().endswith(")"):
            # One-line call like: var = func_name(session_context=session_context)
            # Need to check if audit_service already present
            if "audit_service=" in result[call_line]:
                continue
            # Convert to multi-line or add inline
            # Find the content between parens
            line = result[call_line]
            paren_start = line.index("(")
            paren_end = line.rindex(")")
            inner = line[paren_start + 1:paren_end].strip()
            
            base_indent = "    "  # Registry function indent
            arg_indent = "        "  # Argument indent
            
            assignment = line[:line.index("=") + 2].strip()
            if inner:
                new_lines = [
                    f"    {assignment}{func_name}(",
                    f"        {inner},",
                    f"        audit_service=audit_service,",
                    f"    )",
                ]
            else:
                new_lines = [
                    f"    {assignment}{func_name}(",
                    f"        audit_service=audit_service,",
                    f"    )",
                ]
            result[call_line:call_line + 1] = new_lines
            print(f"  + Wired audit_service in {func_name}() registry call")
            continue
        
        # Multi-line call - find closing paren
        call_end = None
        for i in range(call_line + 1, min(call_line + 20, len(result))):
            if result[i].strip() == ")":
                call_end = i
                break
        
        if call_end is not None:
            # Check if already has audit_service
            has_audit = False
            for i in range(call_line, call_end + 1):
                if "audit_service=" in result[i]:
                    has_audit = True
                    break
            
            if not has_audit:
                result.insert(call_end, "        audit_service=audit_service,")
                print(f"  + Wired audit_service in {func_name}() registry call")
    
    return result


def main():
    content = FACTORIES_PATH.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    new_lines = process_lines(lines)
    
    new_content = "\n".join(new_lines)
    if new_content != content:
        FACTORIES_PATH.write_text(new_content, encoding="utf-8")
        print(f"\nfactories.py updated successfully")
    else:
        print(f"\nNo changes needed")


if __name__ == "__main__":
    main()
