"""Instrument service files with audit logging boilerplate.

This script adds only the SAFE mechanical parts:
1. TYPE_CHECKING import for AuditService  
2. audit_service optional parameter to __init__
3. self._audit_service assignment in __init__ body
4. _record_audit helper method at end of class

It does NOT insert audit calls at commit points — those are added
manually via targeted edits to ensure correctness.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src" / "seeker_accounting"

# (file_path, module_code_constant)
SERVICES = [
    (ROOT / "modules" / "customers" / "services" / "customer_service.py", "MODULE_CUSTOMERS"),
    (ROOT / "modules" / "suppliers" / "services" / "supplier_service.py", "MODULE_SUPPLIERS"),
    (ROOT / "modules" / "sales" / "services" / "sales_invoice_service.py", "MODULE_SALES"),
    (ROOT / "modules" / "sales" / "services" / "sales_invoice_posting_service.py", "MODULE_SALES"),
    (ROOT / "modules" / "sales" / "services" / "customer_receipt_service.py", "MODULE_SALES"),
    (ROOT / "modules" / "sales" / "services" / "customer_receipt_posting_service.py", "MODULE_SALES"),
    (ROOT / "modules" / "purchases" / "services" / "purchase_bill_service.py", "MODULE_PURCHASES"),
    (ROOT / "modules" / "purchases" / "services" / "purchase_bill_posting_service.py", "MODULE_PURCHASES"),
    (ROOT / "modules" / "purchases" / "services" / "supplier_payment_service.py", "MODULE_PURCHASES"),
    (ROOT / "modules" / "purchases" / "services" / "supplier_payment_posting_service.py", "MODULE_PURCHASES"),
    (ROOT / "modules" / "treasury" / "services" / "financial_account_service.py", "MODULE_TREASURY"),
    (ROOT / "modules" / "treasury" / "services" / "treasury_transaction_service.py", "MODULE_TREASURY"),
    (ROOT / "modules" / "treasury" / "services" / "treasury_transaction_posting_service.py", "MODULE_TREASURY"),
    (ROOT / "modules" / "treasury" / "services" / "treasury_transfer_service.py", "MODULE_TREASURY"),
    (ROOT / "modules" / "treasury" / "services" / "treasury_transfer_posting_service.py", "MODULE_TREASURY"),
    (ROOT / "modules" / "treasury" / "services" / "bank_statement_service.py", "MODULE_TREASURY"),
    (ROOT / "modules" / "treasury" / "services" / "bank_reconciliation_service.py", "MODULE_TREASURY"),
    (ROOT / "modules" / "inventory" / "services" / "item_service.py", "MODULE_INVENTORY"),
    (ROOT / "modules" / "inventory" / "services" / "item_category_service.py", "MODULE_INVENTORY"),
    (ROOT / "modules" / "inventory" / "services" / "unit_of_measure_service.py", "MODULE_INVENTORY"),
    (ROOT / "modules" / "inventory" / "services" / "inventory_location_service.py", "MODULE_INVENTORY"),
    (ROOT / "modules" / "inventory" / "services" / "inventory_document_service.py", "MODULE_INVENTORY"),
    (ROOT / "modules" / "inventory" / "services" / "inventory_posting_service.py", "MODULE_INVENTORY"),
    (ROOT / "modules" / "fixed_assets" / "services" / "asset_service.py", "MODULE_FIXED_ASSETS"),
    (ROOT / "modules" / "fixed_assets" / "services" / "asset_category_service.py", "MODULE_FIXED_ASSETS"),
    (ROOT / "modules" / "fixed_assets" / "services" / "depreciation_run_service.py", "MODULE_FIXED_ASSETS"),
    (ROOT / "modules" / "fixed_assets" / "services" / "depreciation_posting_service.py", "MODULE_FIXED_ASSETS"),
    (ROOT / "modules" / "companies" / "services" / "company_service.py", "MODULE_COMPANIES"),
    (ROOT / "modules" / "accounting" / "reference_data" / "services" / "reference_data_service.py", "MODULE_REFERENCE_DATA"),
    (ROOT / "modules" / "accounting" / "reference_data" / "services" / "tax_setup_service.py", "MODULE_REFERENCE_DATA"),
    (ROOT / "modules" / "contracts_projects" / "services" / "contract_service.py", "MODULE_CONTRACTS"),
    (ROOT / "modules" / "contracts_projects" / "services" / "project_service.py", "MODULE_PROJECTS"),
    (ROOT / "modules" / "budgeting" / "services" / "budget_approval_service.py", "MODULE_BUDGETING"),
    (ROOT / "modules" / "budgeting" / "services" / "project_budget_service.py", "MODULE_BUDGETING"),
]


def instrument_boilerplate(fpath: Path, module_code: str) -> tuple[str, bool]:
    """Add audit boilerplate to a service file (imports, constructor param, helper).
    
    Returns (filename, was_modified).
    """
    if not fpath.exists():
        return (str(fpath.name), False)
    
    content = fpath.read_text(encoding="utf-8")
    original = content
    
    if "_record_audit" in content:
        return (str(fpath.name), False)  # Already instrumented
    
    lines = content.split("\n")
    
    # ── 1. Ensure TYPE_CHECKING is imported from typing ──
    has_typing_import = False
    typing_import_line = None
    for i, line in enumerate(lines):
        if re.match(r"from typing import ", line):
            has_typing_import = True
            typing_import_line = i
            break
    
    if has_typing_import and "TYPE_CHECKING" not in lines[typing_import_line]:
        lines[typing_import_line] = lines[typing_import_line].replace(
            "from typing import ",
            "from typing import TYPE_CHECKING, ",
        )
    elif not has_typing_import:
        # Insert after __future__ import
        for i, line in enumerate(lines):
            if line.startswith("from __future__"):
                lines.insert(i + 1, "")
                lines.insert(i + 2, "from typing import TYPE_CHECKING")
                break
    
    # ── 2. Add TYPE_CHECKING block with AuditService import ──
    if "if TYPE_CHECKING:" not in "\n".join(lines):
        # Find last top-level import line
        last_import_idx = 0
        in_multiline = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and not stripped.startswith("from __future__"):
                last_import_idx = i
                if "(" in stripped and ")" not in stripped:
                    in_multiline = True
            elif in_multiline:
                last_import_idx = i
                if ")" in stripped:
                    in_multiline = False
        
        tc_block = [
            "",
            "if TYPE_CHECKING:",
            "    from seeker_accounting.modules.audit.services.audit_service import AuditService",
        ]
        for j, tc_line in enumerate(tc_block):
            lines.insert(last_import_idx + 1 + j, tc_line)
    
    # ── 3. Add audit_service param to __init__ ──
    # Find ") -> None:" that closes __init__
    in_init = False
    for i, line in enumerate(lines):
        if "def __init__(" in line:
            in_init = True
        if in_init and line.strip() == ") -> None:":
            lines.insert(i, "        audit_service: AuditService | None = None,")
            break
    
    # ── 4. Add self._audit_service = audit_service in __init__ body ──
    # Find the last self._xxx = xxx assignment in __init__
    in_init = False
    last_self_assign = None
    for i, line in enumerate(lines):
        if "def __init__(" in line:
            in_init = True
            continue
        if in_init and line.strip().startswith("def ") and not line.strip().startswith("def __init__"):
            break
        if in_init and re.match(r"        self\._\w+ = \w+", line):
            last_self_assign = i
    
    if last_self_assign is not None:
        lines.insert(last_self_assign + 1, "        self._audit_service = audit_service")
    
    # ── 5. Add _record_audit helper at end of class ──
    helper_lines = [
        "",
        "    def _record_audit(",
        "        self,",
        "        company_id: int,",
        "        event_type_code: str,",
        "        entity_type: str,",
        "        entity_id: int | None,",
        "        description: str,",
        "    ) -> None:",
        "        if self._audit_service is None:",
        "            return",
        "        from seeker_accounting.modules.audit.dto.audit_event_dto import RecordAuditEventCommand",
        f"        from seeker_accounting.modules.audit.event_type_catalog import {module_code}",
        "        try:",
        "            self._audit_service.record_event(",
        "                company_id,",
        "                RecordAuditEventCommand(",
        "                    event_type_code=event_type_code,",
        f"                    module_code={module_code},",
        "                    entity_type=entity_type,",
        "                    entity_id=entity_id,",
        "                    description=description,",
        "                ),",
        "            )",
        "        except Exception:",
        "            pass  # Audit must not break business operations",
    ]
    
    # Append before trailing blank lines
    while lines and lines[-1].strip() == "":
        lines.pop()
    lines.extend(helper_lines)
    lines.append("")

    content = "\n".join(lines)
    if content != original:
        fpath.write_text(content, encoding="utf-8")
        return (str(fpath.name), True)
    return (str(fpath.name), False)


def main() -> None:
    modified = []
    skipped = []
    missing = []
    
    for fpath, module_code in SERVICES:
        if not fpath.exists():
            missing.append(str(fpath.name))
            continue
        name, was_modified = instrument_boilerplate(fpath, module_code)
        if was_modified:
            modified.append(name)
        else:
            skipped.append(name)
    
    print(f"\n=== Audit Boilerplate Instrumentation ===")
    print(f"Modified: {len(modified)}")
    for f in modified:
        print(f"  + {f}")
    print(f"Skipped (already done or no change): {len(skipped)}")
    for f in skipped:
        print(f"  ~ {f}")
    if missing:
        print(f"Missing files: {len(missing)}")
        for f in missing:
            print(f"  ! {f}")


if __name__ == "__main__":
    main()
