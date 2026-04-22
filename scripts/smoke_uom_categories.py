#!/usr/bin/env python
"""Smoke test for UoM categories and conversions."""

from decimal import Decimal
from datetime import date
import uuid
from shared.bootstrap import bootstrap_script_runtime


def main():
    ctx = bootstrap_script_runtime()
    registry = ctx.service_registry
    def main():
        # Permissions needed for this test
        perms = [
            "chart.accounts.create",
            "items.create",
            "locations.create",
            "uom.create",
            "inventory.documents.create",
            "inventory.documents.post",
        ]
        ctx = bootstrap_script_runtime(permission_snapshot=perms)
        registry = ctx.service_registry
    
    companies = registry.company_service.list_companies()
    if not companies:
        print("✗ No companies found")
        return False
    
    company_id = companies[0].id
    print(f"Using company id={company_id}")
    
    # Create UoM category
    print("\n=== Testing UoM Categories ===")
    from seeker_accounting.modules.inventory.dto.inventory_reference_commands import CreateUomCategoryCommand
    
    unique_code = f"PKG{str(uuid.uuid4())[:8]}"
    cat_cmd = CreateUomCategoryCommand(code=unique_code, name="Packaging")
    category = registry.uom_category_service.create_category(company_id, cat_cmd)
    print(f"✓ Created category: {category.code}")
    
    # Create UoMs
    print("\n=== Testing UoM Creation with Ratios ===")
    from seeker_accounting.modules.inventory.dto.inventory_reference_commands import CreateUnitOfMeasureCommand
    
    pcs_code = f"PCS{str(uuid.uuid4())[:8]}"
    pcs_uom = registry.unit_of_measure_service.create_unit_of_measure(
        company_id,
        CreateUnitOfMeasureCommand(code=pcs_code, name="Pieces", category_id=category.id, ratio_to_base=Decimal("1"))
    )
    print(f"✓ Created UoM: {pcs_uom.code} (ratio={pcs_uom.ratio_to_base})")
    
    pkt_code = f"PKT{str(uuid.uuid4())[:8]}"
    pkt_uom = registry.unit_of_measure_service.create_unit_of_measure(
        company_id,
        CreateUnitOfMeasureCommand(code=pkt_code, name="Packet", category_id=category.id, ratio_to_base=Decimal("10"))
    )
    print(f"✓ Created UoM: {pkt_uom.code} (ratio={pkt_uom.ratio_to_base})")
    
    ctn_code = f"CTN{str(uuid.uuid4())[:8]}"
    ctn_uom = registry.unit_of_measure_service.create_unit_of_measure(
        company_id,
        CreateUnitOfMeasureCommand(code=ctn_code, name="Carton", category_id=category.id, ratio_to_base=Decimal("120"))
    )
    print(f"✓ Created UoM: {ctn_uom.code} (ratio={ctn_uom.ratio_to_base})")
    
    # Test conversion
    print("\n=== Testing UoM Conversion ===")
    result = registry.unit_of_measure_service.convert_quantity(company_id, ctn_uom.id, pkt_uom.id, Decimal("2"))
    print(f"✓ Convert 2 CTN to PKT: {result} (expected 24)")
    if result != Decimal("24"):
        print(f"✗ Conversion failed")
        return False
    
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED!")
    print("="*60)
    return True


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
