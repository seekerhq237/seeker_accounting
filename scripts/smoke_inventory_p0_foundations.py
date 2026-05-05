"""Smoke for inventory upgrade plan Phase 0 (Slices 1.1–1.4).

Exercises the new platform pieces shipped in Phase 0:

* Slice 1.4 — ``InventoryReferenceDataService.list_document_types`` /
  ``list_reason_codes`` returning the 21 document types and 11 reason codes
  seeded by the migration.
* Slice 1.3 — ``ItemUomConversionService.create_uom_conversion`` and
  ``convert_to_base_quantity``.
* Slice 1.3 — ``ItemAccountOverrideService.create_override`` and
  ``ItemAccountResolverService.resolve_accounts`` honouring per-(item, location)
  overrides.
* Slice 1.1 — ``ItemService.create_item`` accepting ``standard_cost``,
  ``lifecycle_status_code`` and stockable/sellable/purchasable flags.
* Slice 1.2 — Drafting a ``goods_receipt_purchase`` document and posting it
  via the existing ``InventoryPostingService`` (now resolving the new
  catalog code through ``_DOC_TYPE_ACTION``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.modules.accounting.chart_of_accounts.dto.account_commands import (
    CreateAccountCommand,
)
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.administration.rbac_catalog import SYSTEM_PERMISSION_BY_CODE
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CreateInventoryDocumentCommand,
    InventoryDocumentLineCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_commands import (
    CreateInventoryLocationCommand,
    CreateUnitOfMeasureCommand,
)
from seeker_accounting.modules.inventory.dto.item_commands import (
    CreateItemAccountOverrideCommand,
    CreateItemCommand,
    CreateItemUomConversionCommand,
)


def main() -> int:  # noqa: C901, PLR0915
    app = QApplication([])
    bootstrap = bootstrap_script_runtime(
        app,
        permission_snapshot=tuple(SYSTEM_PERMISSION_BY_CODE.keys()),
    )
    registry = bootstrap.service_registry

    failures: list[str] = []

    def check(label: str, cond: bool) -> None:
        marker = "[PASS]" if cond else "[FAIL]"
        print(f"  {marker} {label}")
        if not cond:
            failures.append(label)

    # 1. Company + chart + fiscal + sequences
    import uuid as _uuid
    suffix = _uuid.uuid4().hex[:6].upper()
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Inv P0 Smoke {suffix} SARL",
            display_name=f"Inv P0 Smoke {suffix}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    cid = company.id
    print(f"\nCompany id={cid}")

    registry.chart_seed_service.ensure_global_chart_reference_seed()
    registry.company_seed_service.seed_built_in_chart(cid)

    fy = registry.fiscal_calendar_service.create_fiscal_year(
        cid,
        CreateFiscalYearCommand(
            year_code="FY2026",
            year_name="Fiscal Year 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        ),
    )
    registry.fiscal_calendar_service.generate_periods(
        cid, fy.id, GenerateFiscalPeriodsCommand(opening_status_code="OPEN")
    )

    for doc_type, prefix in (
        ("JOURNAL_ENTRY", "JRN-"),
        ("INVENTORY_DOCUMENT", "INV-"),
    ):
        registry.numbering_setup_service.create_document_sequence(
            cid,
            CreateDocumentSequenceCommand(
                document_type_code=doc_type, prefix=prefix, next_number=1, padding_width=4
            ),
        )

    # 2. Slice 1.4 — Reference catalog seeded by service for the new company.
    print("\n--- Slice 1.4: reference catalog ---")
    registry.inventory_reference_data_service.ensure_document_types_seeded(cid)
    registry.inventory_reference_data_service.ensure_standard_reason_codes(cid)
    doc_types = registry.inventory_reference_data_service.list_document_types(cid)
    check("21 document types are visible", len(doc_types) == 21)
    code_set = {dt.code for dt in doc_types}
    check("goods_receipt_purchase code exists", "goods_receipt_purchase" in code_set)
    check("transfer_in_transit code exists", "transfer_in_transit" in code_set)

    reason_codes = registry.inventory_reference_data_service.list_reason_codes(cid)
    check("11 reason codes are visible", len(reason_codes) == 11)

    # Re-seeding is idempotent — no duplicate rows.
    registry.inventory_reference_data_service.ensure_document_types_seeded(cid)
    registry.inventory_reference_data_service.ensure_standard_reason_codes(cid)
    doc_types_2 = registry.inventory_reference_data_service.list_document_types(cid)
    reason_codes_2 = registry.inventory_reference_data_service.list_reason_codes(cid)
    check("ensure_document_types_seeded is idempotent", len(doc_types_2) == 21)
    check("ensure_standard_reason_codes is idempotent", len(reason_codes_2) == 11)

    # 3. Reference rows + GL accounts
    uom_pcs = registry.unit_of_measure_service.create_unit_of_measure(
        cid, CreateUnitOfMeasureCommand(code="PCS", name="Pieces")
    )
    uom_box = registry.unit_of_measure_service.create_unit_of_measure(
        cid, CreateUnitOfMeasureCommand(code="BOX", name="Box of 12")
    )
    loc_main = registry.inventory_location_service.create_inventory_location(
        cid, CreateInventoryLocationCommand(code="MAIN", name="Main Warehouse")
    )
    loc_b = registry.inventory_location_service.create_inventory_location(
        cid, CreateInventoryLocationCommand(code="STORE-B", name="Store B")
    )

    types = registry.reference_data_service.list_account_types()
    classes = registry.reference_data_service.list_account_classes()
    debit_type = next(t for t in types if t.normal_balance == "DEBIT")

    def _new_account(code: str, name: str) -> int:
        return registry.chart_of_accounts_service.create_account(
            cid,
            CreateAccountCommand(
                account_code=code,
                account_name=name,
                account_class_id=classes[0].id,
                account_type_id=debit_type.id,
                normal_balance=debit_type.normal_balance,
                allow_manual_posting=True,
                is_control_account=False,
            ),
        ).id

    inv_account = _new_account("1310", "Inventory Stock")
    cogs_account = _new_account("5100", "Cost of Goods Sold")
    expense_account = _new_account("6100", "Inventory Adjustments")
    inv_account_b = _new_account("1311", "Inventory Stock — Store B")

    # 4. Slice 1.1 — Item with new lifecycle / classifier columns.
    print("\n--- Slice 1.1: item lifecycle and classifiers ---")
    item = registry.item_service.create_item(
        cid,
        CreateItemCommand(
            item_code="WIDGET-001",
            item_name="Standard Widget",
            item_type_code="stock",
            unit_of_measure_id=uom_pcs.id,
            inventory_cost_method_code="weighted_average",
            inventory_account_id=inv_account,
            cogs_account_id=cogs_account,
            expense_account_id=expense_account,
            standard_cost=Decimal("12.500000"),
            lifecycle_status_code="active",
            is_sellable=True,
            is_purchasable=True,
            is_stockable=True,
            ohada_stock_class_code="merchandise",
        ),
    )
    check("item created with new fields", item.lifecycle_status_code == "active")
    check("standard_cost stored", item.standard_cost == Decimal("12.500000"))
    check("ohada_stock_class_code stored", item.ohada_stock_class_code == "merchandise")
    check("is_sellable/is_stockable/is_purchasable defaulted", all((item.is_sellable, item.is_stockable, item.is_purchasable)))

    # 5. Slice 1.3 — UoM conversion.
    print("\n--- Slice 1.3: item UoM conversion ---")
    conversion = registry.item_uom_conversion_service.create_conversion(
        cid,
        CreateItemUomConversionCommand(
            item_id=item.id,
            unit_of_measure_id=uom_box.id,
            ratio_to_base=Decimal("12.000000"),
            rounding_rule_code="none",
            is_purchase_default=True,
            is_sales_default=False,
            is_stocking=False,
        ),
    )
    check("conversion created", conversion.ratio_to_base == Decimal("12.000000"))

    # convert_to_base_quantity must be called inside a session.
    with bootstrap.session_context.unit_of_work_factory() as uow:
        base_qty, ratio = registry.item_uom_conversion_service.convert_to_base_quantity(
            uow.session,
            company_id=cid,
            item_id=item.id,
            unit_of_measure_id=uom_box.id,
            quantity=Decimal("3"),
        )
    check("3 BOX -> 36 base PCS", base_qty == Decimal("36.0000"))
    check("ratio echoed", ratio == Decimal("12.000000"))

    with bootstrap.session_context.unit_of_work_factory() as uow:
        base_qty_pcs, ratio_pcs = registry.item_uom_conversion_service.convert_to_base_quantity(
            uow.session,
            company_id=cid,
            item_id=item.id,
            unit_of_measure_id=uom_pcs.id,
            quantity=Decimal("5"),
        )
    check("5 PCS (base) -> 5 base PCS", base_qty_pcs == Decimal("5.0000") and ratio_pcs == Decimal("1"))

    # 6. Slice 1.3 — Account overrides.
    print("\n--- Slice 1.3: item account overrides ---")
    registry.item_account_override_service.create_override(
        cid,
        CreateItemAccountOverrideCommand(
            item_id=item.id,
            location_id=loc_b.id,
            inventory_account_id=inv_account_b,
        ),
    )
    resolved_main = registry.item_account_resolver_service.resolve_accounts(
        company_id=cid, item_id=item.id, location_id=loc_main.id
    )
    resolved_b = registry.item_account_resolver_service.resolve_accounts(
        company_id=cid, item_id=item.id, location_id=loc_b.id
    )
    check(
        "MAIN resolves to item's own inventory account",
        resolved_main.inventory_account_id == inv_account,
    )
    check(
        "STORE-B resolves to override inventory account",
        resolved_b.inventory_account_id == inv_account_b,
    )

    # 7. Slice 1.2/1.4 — draft a goods_receipt_purchase document and post it.
    print("\n--- Slice 1.2/1.4: goods_receipt_purchase posting ---")
    goods_receipt_doc_type = next(
        dt for dt in doc_types if dt.code == "goods_receipt_purchase"
    )
    received_reason = next(rc for rc in reason_codes if rc.code == "opening_balance")

    draft = registry.inventory_document_service.create_draft_document(
        cid,
        CreateInventoryDocumentCommand(
            document_type_code=goods_receipt_doc_type.code,
            document_date=date(2026, 1, 5),
            location_id=loc_main.id,
            reference_number="PO-1001",
            notes="Phase 0 smoke",
            reason_code_id=received_reason.id,
            source_module_code="inventory",
            source_document_type="manual",
            source_document_id=None,
            lines=(
                InventoryDocumentLineCommand(
                    item_id=item.id,
                    quantity=Decimal("10"),
                    unit_cost=Decimal("12.50"),
                    counterparty_account_id=expense_account,
                ),
            ),
        ),
    )
    check("draft has new code", draft.document_type_code == "goods_receipt_purchase")
    check("draft carried reason_code", draft.reason_code_code == "opening_balance")

    posted = registry.inventory_posting_service.post_inventory_document(cid, draft.id)
    check("document posted with JE", posted.journal_entry_id is not None and posted.journal_entry_id > 0)
    check("posted document_id matches", posted.document_id == draft.id)

    print("\n=========================")
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
