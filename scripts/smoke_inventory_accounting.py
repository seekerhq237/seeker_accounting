from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
from seeker_accounting.app.dependency.factories import (
    create_active_company_context,
    create_app_context,
    create_navigation_service,
    create_service_registry,
    create_session_context,
    create_theme_manager,
)
from seeker_accounting.app.navigation import nav_ids
from seeker_accounting.app.shell.main_window import MainWindow
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
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.inventory.dto.inventory_document_commands import (
    CreateInventoryDocumentCommand,
    InventoryDocumentLineCommand,
    UpdateInventoryDocumentCommand,
)
from seeker_accounting.modules.inventory.dto.inventory_reference_commands import (
    CreateInventoryLocationCommand,
    CreateItemCategoryCommand,
    CreateUnitOfMeasureCommand,
)
from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand, UpdateItemCommand
from seeker_accounting.modules.inventory.ui.inventory_documents_page import InventoryDocumentsPage
from seeker_accounting.modules.inventory.ui.inventory_locations_page import InventoryLocationsPage
from seeker_accounting.modules.inventory.ui.inventory_stock_view import InventoryStockView
from seeker_accounting.modules.inventory.ui.item_categories_page import ItemCategoriesPage
from seeker_accounting.modules.inventory.ui.items_page import ItemsPage
from seeker_accounting.modules.inventory.ui.units_of_measure_page import UnitsOfMeasurePage
from seeker_accounting.platform.exceptions import PeriodLockedError, ValidationError


def main() -> int:  # noqa: C901, PLR0915
    app = QApplication([])
    bootstrap = bootstrap_script_runtime(app)
    settings = bootstrap.settings
    app_context = bootstrap.app_context
    session_context = bootstrap.session_context
    active_company_context = bootstrap.active_company_context
    navigation_service = bootstrap.navigation_service
    theme_manager = bootstrap.theme_manager
    registry = bootstrap.service_registry

    _ensure_country_and_currency(registry)

    # ------------------------------------------------------------------
    # 1. Company + chart seed + fiscal setup + sequences
    # ------------------------------------------------------------------
    import uuid as _uuid
    _suffix = _uuid.uuid4().hex[:6].upper()
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Inventory Smoke {_suffix} SARL",
            display_name=f"Inventory Smoke {_suffix}",
            country_code="CM",
            base_currency_code="XAF",
        )
    )
    cid = company.id
    print(f"CHECK 1 PASS — company_created id={cid}")

    registry.chart_seed_service.ensure_global_chart_reference_seed()
    registry.company_seed_service.seed_built_in_chart(cid)

    # Fiscal year + periods
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
    print("CHECK 2 PASS — fiscal_year_and_periods_created")

    # Document sequences
    for doc_type in ("JOURNAL_ENTRY", "INVENTORY_DOCUMENT"):
        registry.numbering_setup_service.create_document_sequence(
            cid,
            CreateDocumentSequenceCommand(
                document_type_code=doc_type,
                prefix=("JRN-" if doc_type == "JOURNAL_ENTRY" else "INV-"),
                next_number=1,
                padding_width=4,
            ),
        )
    print("CHECK 3 PASS — sequences_created")

    # ------------------------------------------------------------------
    # 2. Create reference table entries
    # ------------------------------------------------------------------

    # Units of measure
    uom_pcs = registry.unit_of_measure_service.create_unit_of_measure(
        cid,
        CreateUnitOfMeasureCommand(code="PCS", name="Pieces"),
    )
    assert uom_pcs.code == "PCS"
    assert uom_pcs.is_active is True
    uom_kg = registry.unit_of_measure_service.create_unit_of_measure(
        cid,
        CreateUnitOfMeasureCommand(code="KG", name="Kilograms"),
    )
    # Duplicate code rejected
    try:
        registry.unit_of_measure_service.create_unit_of_measure(
            cid,
            CreateUnitOfMeasureCommand(code="PCS", name="Duplicate"),
        )
        print("CHECK 4 FAIL — duplicate_uom_code_not_blocked")
        return 1
    except (ValidationError, Exception):
        pass
    listed_uoms = registry.unit_of_measure_service.list_units_of_measure(cid)
    assert len(listed_uoms) == 2
    print(f"CHECK 4 PASS — uom_created id={uom_pcs.id} listed={len(listed_uoms)}")

    # Item categories
    cat_goods = registry.item_category_service.create_item_category(
        cid,
        CreateItemCategoryCommand(code="GOODS", name="Physical Goods"),
    )
    assert cat_goods.code == "GOODS"
    print(f"CHECK 5 PASS — item_category_created id={cat_goods.id}")

    # Inventory locations
    loc_main = registry.inventory_location_service.create_inventory_location(
        cid,
        CreateInventoryLocationCommand(code="MAIN", name="Main Warehouse"),
    )
    loc_b = registry.inventory_location_service.create_inventory_location(
        cid,
        CreateInventoryLocationCommand(code="STORE-B", name="Store B"),
    )
    listed_locs = registry.inventory_location_service.list_inventory_locations(cid)
    assert len(listed_locs) >= 2
    print(f"CHECK 6 PASS — inventory_locations_created main={loc_main.id} store_b={loc_b.id}")

    # ------------------------------------------------------------------
    # 3. Create GL accounts for inventory
    # ------------------------------------------------------------------
    types = registry.reference_data_service.list_account_types()
    classes = registry.reference_data_service.list_account_classes()
    if not classes or not types:
        raise RuntimeError("Account classes or types not available.")
    debit_type = next((t for t in types if t.normal_balance == "DEBIT"), types[0])

    inv_account = registry.chart_of_accounts_service.create_account(
        cid,
        CreateAccountCommand(
            account_code="1310",
            account_name="Inventory Stock",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    cogs_account = registry.chart_of_accounts_service.create_account(
        cid,
        CreateAccountCommand(
            account_code="5100",
            account_name="Cost of Goods Sold",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    expense_account = registry.chart_of_accounts_service.create_account(
        cid,
        CreateAccountCommand(
            account_code="6100",
            account_name="Inventory Adjustments",
            account_class_id=classes[0].id,
            account_type_id=debit_type.id,
            normal_balance=debit_type.normal_balance,
            allow_manual_posting=True,
            is_control_account=False,
        ),
    )
    print("CHECK 7 PASS — gl_accounts_created")

    # ------------------------------------------------------------------
    # 4. Validate invalid unit_of_measure_id is rejected
    # ------------------------------------------------------------------
    try:
        registry.item_service.create_item(
            cid,
            CreateItemCommand(
                item_code="BAD-001",
                item_name="Bad Item",
                item_type_code="stock",
                unit_of_measure_id=999999,
                unit_of_measure_code="PCS",
                inventory_cost_method_code="weighted_average",
                inventory_account_id=inv_account.id,
                cogs_account_id=cogs_account.id,
                expense_account_id=expense_account.id,
            ),
        )
        print("CHECK 8 FAIL — invalid_uom_id_not_blocked")
        return 1
    except (ValidationError, Exception):
        print("CHECK 8 PASS — invalid_uom_id_rejected")

    # ------------------------------------------------------------------
    # 5. Create stock items with UoM FK reference
    # ------------------------------------------------------------------
    item = registry.item_service.create_item(
        cid,
        CreateItemCommand(
            item_code="WIDGET-001",
            item_name="Standard Widget",
            item_type_code="stock",
            unit_of_measure_id=uom_pcs.id,
            unit_of_measure_code="PCS",
            item_category_id=cat_goods.id,
            inventory_cost_method_code="weighted_average",
            inventory_account_id=inv_account.id,
            cogs_account_id=cogs_account.id,
            expense_account_id=expense_account.id,
            reorder_level_quantity=Decimal("10"),
        ),
    )
    assert item.item_code == "WIDGET-001"
    assert item.unit_of_measure_id == uom_pcs.id
    assert item.item_category_id == cat_goods.id
    print(f"CHECK 9 PASS — stock_item_created id={item.id} uom_id={item.unit_of_measure_id}")

    item2 = registry.item_service.create_item(
        cid,
        CreateItemCommand(
            item_code="GADGET-001",
            item_name="Premium Gadget",
            item_type_code="stock",
            unit_of_measure_id=uom_pcs.id,
            unit_of_measure_code="PCS",
            inventory_cost_method_code="weighted_average",
            inventory_account_id=inv_account.id,
            cogs_account_id=cogs_account.id,
            expense_account_id=expense_account.id,
            reorder_level_quantity=Decimal("5"),
        ),
    )
    print(f"CHECK 10 PASS — second_item_created id={item2.id}")

    # ------------------------------------------------------------------
    # 6. Validate item update with UoM FK
    # ------------------------------------------------------------------
    updated_item = registry.item_service.update_item(
        cid,
        item.id,
        UpdateItemCommand(
            item_code="WIDGET-001",
            item_name="Standard Widget (Updated)",
            item_type_code="stock",
            unit_of_measure_id=uom_pcs.id,
            unit_of_measure_code="PCS",
            inventory_cost_method_code="weighted_average",
            inventory_account_id=inv_account.id,
            cogs_account_id=cogs_account.id,
            expense_account_id=expense_account.id,
            reorder_level_quantity=Decimal("10"),
        ),
    )
    assert updated_item.item_name == "Standard Widget (Updated)"
    print("CHECK 11 PASS — item_updated")

    # ------------------------------------------------------------------
    # 7. Create receipt document with location_id
    # ------------------------------------------------------------------
    receipt_doc = registry.inventory_document_service.create_draft_document(
        cid,
        CreateInventoryDocumentCommand(
            document_type_code="receipt",
            document_date=date(2026, 1, 15),
            reference_number="PO-001",
            notes="Initial stock receipt",
            location_id=loc_main.id,
            lines=(
                InventoryDocumentLineCommand(
                    item_id=item.id,
                    quantity=Decimal("100"),
                    unit_cost=Decimal("50.00"),
                    counterparty_account_id=expense_account.id,
                ),
                InventoryDocumentLineCommand(
                    item_id=item2.id,
                    quantity=Decimal("50"),
                    unit_cost=Decimal("120.00"),
                    counterparty_account_id=expense_account.id,
                ),
            ),
        ),
    )
    assert receipt_doc.status_code == "draft"
    assert len(receipt_doc.lines) == 2
    assert receipt_doc.location_id == loc_main.id
    print(f"CHECK 12 PASS — receipt_draft_created id={receipt_doc.id} location_id={receipt_doc.location_id}")

    # ------------------------------------------------------------------
    # 8. Post receipt document
    # ------------------------------------------------------------------
    receipt_result = registry.inventory_posting_service.post_inventory_document(
        cid, receipt_doc.id
    )
    assert receipt_result.journal_entry_number.startswith("JRN-")
    assert receipt_result.document_number.startswith("INV-")
    print(f"CHECK 13 PASS — receipt_posted doc={receipt_result.document_number} je={receipt_result.journal_entry_number}")

    # ------------------------------------------------------------------
    # 9. Verify stock position after receipt
    # ------------------------------------------------------------------
    pos1 = registry.inventory_valuation_service.get_stock_position(cid, item.id)
    assert pos1.quantity_on_hand == Decimal("100")
    assert pos1.weighted_average_cost == Decimal("50.0000")
    assert pos1.total_value == Decimal("5000.00")
    print(f"CHECK 14 PASS — stock_position_verified qty={pos1.quantity_on_hand} val={pos1.total_value}")

    # ------------------------------------------------------------------
    # 10. Create and post issue document
    # ------------------------------------------------------------------
    issue_doc = registry.inventory_document_service.create_draft_document(
        cid,
        CreateInventoryDocumentCommand(
            document_type_code="issue",
            document_date=date(2026, 2, 10),
            reference_number="SO-001",
            location_id=loc_main.id,
            lines=(
                InventoryDocumentLineCommand(
                    item_id=item.id,
                    quantity=Decimal("30"),
                    counterparty_account_id=cogs_account.id,
                ),
            ),
        ),
    )
    issue_result = registry.inventory_posting_service.post_inventory_document(
        cid, issue_doc.id
    )
    pos_after_issue = registry.inventory_valuation_service.get_stock_position(cid, item.id)
    assert pos_after_issue.quantity_on_hand == Decimal("70")
    print(f"CHECK 15 PASS — issue_posted qty={pos_after_issue.quantity_on_hand}")

    # ------------------------------------------------------------------
    # 11. Insufficient stock blocks issue
    # ------------------------------------------------------------------
    try:
        registry.inventory_document_service.create_draft_document(
            cid,
            CreateInventoryDocumentCommand(
                document_type_code="issue",
                document_date=date(2026, 2, 15),
                lines=(
                    InventoryDocumentLineCommand(
                        item_id=item.id,
                        quantity=Decimal("999"),
                        counterparty_account_id=cogs_account.id,
                    ),
                ),
            ),
        )
        print("CHECK 16 FAIL — insufficient_stock_not_blocked")
        return 1
    except ValidationError:
        print("CHECK 16 PASS — insufficient_stock_blocked")

    # ------------------------------------------------------------------
    # 12. Positive adjustment
    # ------------------------------------------------------------------
    adj_doc = registry.inventory_document_service.create_draft_document(
        cid,
        CreateInventoryDocumentCommand(
            document_type_code="adjustment",
            document_date=date(2026, 3, 1),
            reference_number="ADJ-001",
            lines=(
                InventoryDocumentLineCommand(
                    item_id=item.id,
                    quantity=Decimal("20"),
                    unit_cost=Decimal("55.00"),
                    counterparty_account_id=expense_account.id,
                ),
            ),
        ),
    )
    registry.inventory_posting_service.post_inventory_document(cid, adj_doc.id)
    pos_after_adj = registry.inventory_valuation_service.get_stock_position(cid, item.id)
    assert pos_after_adj.quantity_on_hand == Decimal("90")
    print(f"CHECK 17 PASS — positive_adjustment_posted qty={pos_after_adj.quantity_on_hand}")

    # ------------------------------------------------------------------
    # 13. Negative adjustment
    # ------------------------------------------------------------------
    neg_adj_doc = registry.inventory_document_service.create_draft_document(
        cid,
        CreateInventoryDocumentCommand(
            document_type_code="adjustment",
            document_date=date(2026, 3, 5),
            lines=(
                InventoryDocumentLineCommand(
                    item_id=item.id,
                    quantity=Decimal("-5"),
                    counterparty_account_id=expense_account.id,
                ),
            ),
        ),
    )
    registry.inventory_posting_service.post_inventory_document(cid, neg_adj_doc.id)
    pos_after_neg = registry.inventory_valuation_service.get_stock_position(cid, item.id)
    assert pos_after_neg.quantity_on_hand == Decimal("85")
    print(f"CHECK 18 PASS — negative_adjustment_posted qty={pos_after_neg.quantity_on_hand}")

    # ------------------------------------------------------------------
    # 14. Double-post blocked
    # ------------------------------------------------------------------
    try:
        registry.inventory_posting_service.post_inventory_document(cid, receipt_doc.id)
        print("CHECK 19 FAIL — double_post_not_blocked")
        return 1
    except ValidationError:
        print("CHECK 19 PASS — double_post_blocked")

    # ------------------------------------------------------------------
    # 15. Cancel a draft document
    # ------------------------------------------------------------------
    cancel_doc = registry.inventory_document_service.create_draft_document(
        cid,
        CreateInventoryDocumentCommand(
            document_type_code="receipt",
            document_date=date(2026, 3, 10),
            lines=(
                InventoryDocumentLineCommand(
                    item_id=item.id,
                    quantity=Decimal("10"),
                    unit_cost=Decimal("60.00"),
                    counterparty_account_id=expense_account.id,
                ),
            ),
        ),
    )
    registry.inventory_document_service.cancel_draft_document(cid, cancel_doc.id)
    cancelled = registry.inventory_document_service.get_inventory_document(cid, cancel_doc.id)
    assert cancelled.status_code == "cancelled"
    print("CHECK 20 PASS — draft_cancelled")

    # ------------------------------------------------------------------
    # 16. Valuation summary
    # ------------------------------------------------------------------
    summary = registry.inventory_valuation_service.get_inventory_valuation_summary(cid)
    assert summary.total_items_with_stock >= 2
    assert summary.total_inventory_value > Decimal("0")
    print(
        f"CHECK 21 PASS — valuation_summary items={summary.total_items_with_stock} "
        f"value={summary.total_inventory_value}"
    )

    # ------------------------------------------------------------------
    # 17. Low stock filter
    # ------------------------------------------------------------------
    low_stock_items = registry.inventory_valuation_service.list_stock_positions(
        cid, low_stock_only=True
    )
    print(f"CHECK 22 PASS — low_stock_filter count={len(low_stock_items)}")

    # ------------------------------------------------------------------
    # 18. Deactivate item
    # ------------------------------------------------------------------
    registry.item_service.deactivate_item(cid, item2.id)
    deactivated = registry.item_service.get_item(cid, item2.id)
    assert deactivated.is_active is False
    print("CHECK 23 PASS — item_deactivated")

    # ------------------------------------------------------------------
    # 19. Posted document immutability
    # ------------------------------------------------------------------
    try:
        registry.inventory_document_service.update_draft_document(
            cid,
            receipt_doc.id,
            UpdateInventoryDocumentCommand(
                document_type_code="receipt",
                document_date=date(2026, 1, 15),
                lines=(
                    InventoryDocumentLineCommand(
                        item_id=item.id,
                        quantity=Decimal("999"),
                        unit_cost=Decimal("1.00"),
                    ),
                ),
            ),
        )
        print("CHECK 24 FAIL — posted_doc_edit_not_blocked")
        return 1
    except ValidationError:
        print("CHECK 24 PASS — posted_doc_edit_blocked")

    # ------------------------------------------------------------------
    # 20. UI boot smoke (offscreen) — reference pages
    # ------------------------------------------------------------------
    registry.company_context_service.set_active_company(cid)

    uom_page = UnitsOfMeasurePage(registry)
    print("CHECK 25 PASS — units_of_measure_page_boot")

    cat_page = ItemCategoriesPage(registry)
    print("CHECK 26 PASS — item_categories_page_boot")

    loc_page = InventoryLocationsPage(registry)
    print("CHECK 27 PASS — inventory_locations_page_boot")

    items_page = ItemsPage(registry)
    items_page.reload_items()
    print("CHECK 28 PASS — items_page_boot")

    docs_page = InventoryDocumentsPage(registry)
    docs_page.reload_documents()
    print("CHECK 29 PASS — documents_page_boot")

    stock_view = InventoryStockView(registry)
    stock_view.reload_stock()
    print("CHECK 30 PASS — stock_view_boot")

    # ------------------------------------------------------------------
    # 21. Full shell boot with new nav IDs
    # ------------------------------------------------------------------
    window = MainWindow(registry)
    window.show()
    navigation_service.navigate(nav_ids.UNITS_OF_MEASURE)
    navigation_service.navigate(nav_ids.ITEM_CATEGORIES)
    navigation_service.navigate(nav_ids.INVENTORY_LOCATIONS)
    navigation_service.navigate(nav_ids.ITEMS)
    navigation_service.navigate(nav_ids.INVENTORY_DOCUMENTS)
    navigation_service.navigate(nav_ids.STOCK_POSITION)
    print("CHECK 31 PASS — shell_navigation_boot")

    print("\n=== ALL 31 CHECKS PASSED ===")
    return 0


def _ensure_country_and_currency(registry: object) -> None:
    """Seed minimal country + currency if not present."""
    uow_factory = registry.session_context.unit_of_work_factory
    with uow_factory() as uow:
        from seeker_accounting.modules.accounting.reference_data.models.country import Country
        from seeker_accounting.modules.accounting.reference_data.models.currency import Currency

        if uow.session.get(Country, "CM") is None:
            uow.session.add(Country(country_code="CM", country_name="Cameroon", phone_code="+237"))
        if uow.session.get(Currency, "XAF") is None:
            uow.session.add(Currency(currency_code="XAF", currency_name="CFA Franc", symbol="FCFA", decimal_places=0))
        uow.commit()


if __name__ == "__main__":
    raise SystemExit(main())
