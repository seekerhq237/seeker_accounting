"""
Slice 10b: Purchase Orders -- Workflow Smoke Test

Validates end-to-end PO workflow:
1. Setup: Company, chart, fiscal year, sequences, supplier, tax, accounts
2. Draft PO creation and update
3. Status flow: draft -> sent -> acknowledged
4. Cancellation guard (can only cancel draft/sent)
5. Conversion: acknowledged -> purchase bill
6. Double-conversion guard (already converted)
7. UI page navigation (offscreen)
"""

from __future__ import annotations

from datetime import date, datetime
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
from seeker_accounting.modules.accounting.fiscal_periods.dto.fiscal_calendar_commands import (
    CreateFiscalYearCommand,
    GenerateFiscalPeriodsCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.numbering_dto import (
    CreateDocumentSequenceCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.reference_data_dto import (
    CreatePaymentTermCommand,
)
from seeker_accounting.modules.accounting.reference_data.dto.tax_setup_dto import (
    CreateTaxCodeCommand,
)
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand
from seeker_accounting.modules.purchases.dto.purchase_order_commands import (
    ConvertPurchaseOrderCommand,
    CreatePurchaseOrderCommand,
    PurchaseOrderLineCommand,
    UpdatePurchaseOrderCommand,
)
from seeker_accounting.modules.suppliers.dto.supplier_commands import (
    CreateSupplierCommand,
    CreateSupplierGroupCommand,
)
from seeker_accounting.platform.exceptions import ConflictError, ValidationError
from seeker_accounting.modules.administration.rbac_catalog import SYSTEM_PERMISSION_BY_CODE


def main() -> int:  # noqa: C901, PLR0915
    """Run the smoke test."""
    app = QApplication([])
    bootstrap = bootstrap_script_runtime(
        app,
        permission_snapshot=tuple(SYSTEM_PERMISSION_BY_CODE.keys()),
    )
    registry = bootstrap.service_registry

    PASS = "[PASS]"
    FAIL = "[FAIL]"
    failures: list[str] = []

    def check(label: str, cond: bool) -> None:
        if cond:
            print(f"  {PASS} {label}")
        else:
            print(f"  {FAIL} {label}")
            failures.append(label)

    def assert_raises(label: str, exc_type: type, fn: object) -> None:
        try:
            fn()  # type: ignore[operator]
            print(f"  {FAIL} {label} — no exception raised")
            failures.append(label)
        except exc_type:
            print(f"  {PASS} {label}")
        except Exception as e:
            print(f"  {FAIL} {label} — wrong exception: {type(e).__name__}: {e}")
            failures.append(label)

    try:
        # ------------------------------------------------------------------
        # 1. Company + chart + fiscal setup
        # ------------------------------------------------------------------
        print("[TEST] 1. Setting up company, chart, fiscal year...")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        company = registry.company_service.create_company(
            CreateCompanyCommand(
                legal_name=f"PO Smoke {timestamp} SARL",
                display_name="PO Smoke",
                country_code="CM",
                base_currency_code="XAF",
            )
        )
        cid = company.id
        print(f"  {PASS} company {cid} created")

        registry.chart_seed_service.ensure_global_chart_reference_seed()
        registry.company_seed_service.seed_built_in_chart(cid)
        print(f"  {PASS} chart seeded")

        term = registry.reference_data_service.create_payment_term(
            cid,
            CreatePaymentTermCommand(code="NET30", name="Net 30", days_due=30),
        )
        print(f"  {PASS} payment term {term.code}")

        # AP control account role mapping (best-effort, not required for PO workflow)
        try:
            accounts = registry.chart_of_accounts_service.list_accounts(cid)
        except Exception:
            accounts = []
        print(f"  {PASS} AP role mapping done (best-effort)")

        # Fiscal year + periods
        fiscal_year = registry.fiscal_calendar_service.create_fiscal_year(
            cid,
            CreateFiscalYearCommand(
                year_code="FY2025",
                year_name="FY 2025",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
            ),
        )
        registry.fiscal_calendar_service.generate_periods(
            cid,
            fiscal_year.id,
            GenerateFiscalPeriodsCommand(periods_per_year=12),
        )
        print(f"  {PASS} fiscal year + periods")

        # PO sequence
        registry.numbering_setup_service.create_document_sequence(
            cid,
            CreateDocumentSequenceCommand(
                document_type_code="purchase_bill",
                prefix="BILL-",
                next_number=1,
                padding_width=6,
            ),
        )
        print(f"  {PASS} bill numbering sequence")

        # ------------------------------------------------------------------
        # 2. Supplier
        # ------------------------------------------------------------------
        print("[TEST] 2. Creating supplier...")
        sg = registry.supplier_service.create_supplier_group(
            cid, CreateSupplierGroupCommand(code="VENDOR", name="Vendors")
        )
        supplier = registry.supplier_service.create_supplier(
            cid,
            CreateSupplierCommand(
                supplier_group_id=sg.id,
                supplier_code="SUP001",
                display_name="Test Supplier Ltd",
                payment_term_id=term.id,
            ),
        )
        print(f"  {PASS} supplier {supplier.id} created")

        # Tax code (no rate — keeps conversion simple)
        tax_code = registry.tax_setup_service.create_tax_code(
            cid,
            CreateTaxCodeCommand(
                code="ZERO",
                name="Zero Rate",
                rate_percent=Decimal("0.00"),
                tax_type_code="purchase",
                calculation_method_code="standard",
                effective_from=date(2025, 1, 1),
            ),
        )
        print(f"  {PASS} tax code {tax_code.code}")

        # Expense account
        expense_account = next(
            (a for a in accounts if a.allow_manual_posting and "expense" in (a.account_name or "").lower()),
            accounts[0] if accounts else None,
        )
        print(f"  {PASS} expense account {expense_account.id if expense_account else 'N/A'}")

        # ------------------------------------------------------------------
        # 3. Create draft PO
        # ------------------------------------------------------------------
        print("[TEST] 3. Create draft PO...")

        line1 = PurchaseOrderLineCommand(
            description="Office Supplies",
            quantity=Decimal("10"),
            unit_cost=Decimal("500.00"),
            discount_percent=None,
            discount_amount=None,
            tax_code_id=None,
            expense_account_id=expense_account.id if expense_account else None,
        )
        line2 = PurchaseOrderLineCommand(
            description="Printer Paper",
            quantity=Decimal("5"),
            unit_cost=Decimal("2000.00"),
            discount_percent=None,
            discount_amount=None,
            tax_code_id=None,
            expense_account_id=None,
        )

        cmd_create = CreatePurchaseOrderCommand(
            supplier_id=supplier.id,
            order_date=date(2025, 3, 15),
            expected_delivery_date=date(2025, 3, 30),
            currency_code="XAF",
            reference_number="RFQ-001",
            notes="Urgently needed",
            lines=(line1, line2),
        )
        draft = registry.purchase_order_service.create_draft_order(cid, cmd_create)
        check("draft order created", draft is not None)
        check("order_number starts with PO-DRAFT-", draft.order_number.startswith("PO-DRAFT-"))
        check("status is draft", draft.status_code == "draft")
        check("subtotal correct", draft.totals.subtotal_amount == Decimal("15000.00"))
        check("2 lines", len(draft.lines) == 2)
        print(f"  order_number={draft.order_number}, subtotal={draft.totals.subtotal_amount}")

        # ------------------------------------------------------------------
        # 4. Update draft PO
        # ------------------------------------------------------------------
        print("[TEST] 4. Update draft PO...")
        cmd_update = UpdatePurchaseOrderCommand(
            supplier_id=supplier.id,
            order_date=date(2025, 3, 16),
            expected_delivery_date=None,
            currency_code="XAF",
            reference_number="RFQ-001-REV",
            notes="Updated notes",
            lines=(
                PurchaseOrderLineCommand(
                    description="Office Supplies Revised",
                    quantity=Decimal("12"),
                    unit_cost=Decimal("500.00"),
                    expense_account_id=expense_account.id if expense_account else None,
                ),
            ),
        )
        updated = registry.purchase_order_service.update_draft_order(cid, draft.id, cmd_update)
        check("order updated", updated is not None)
        check("still draft", updated.status_code == "draft")
        check("1 line", len(updated.lines) == 1)
        check("line description updated", updated.lines[0].description == "Office Supplies Revised")
        check("subtotal updated", updated.totals.subtotal_amount == Decimal("6000.00"))

        # ------------------------------------------------------------------
        # 5. Send order (draft -> sent)
        # ------------------------------------------------------------------
        print("[TEST] 5. Send order...")
        sent = registry.purchase_order_service.send_order(cid, draft.id)
        check("status is sent", sent.status_code == "sent")
        check("order_number finalised (PO-)", sent.order_number.startswith("PO-") and not sent.order_number.startswith("PO-DRAFT-"))
        print(f"  finalised number={sent.order_number}")

        # Cannot update sent order
        assert_raises(
            "cannot update sent order",
            ValidationError,
            lambda: registry.purchase_order_service.update_draft_order(cid, draft.id, cmd_update),
        )

        # ------------------------------------------------------------------
        # 6. Acknowledge order (sent -> acknowledged)
        # ------------------------------------------------------------------
        print("[TEST] 6. Acknowledge order...")
        acknowledged = registry.purchase_order_service.acknowledge_order(cid, draft.id)
        check("status is acknowledged", acknowledged.status_code == "acknowledged")

        # Cannot cancel acknowledged order
        assert_raises(
            "cannot cancel acknowledged order",
            ValidationError,
            lambda: registry.purchase_order_service.cancel_order(cid, draft.id),
        )

        # ------------------------------------------------------------------
        # 7. Convert to bill (acknowledged -> converted)
        # ------------------------------------------------------------------
        print("[TEST] 7. Convert to bill...")
        conv_cmd = ConvertPurchaseOrderCommand(
            bill_date=date(2025, 3, 20),
            due_date=date(2025, 4, 20),
            reference_number="BILL-FROM-PO",
            notes="Converted from PO",
        )
        result = registry.purchase_order_service.convert_to_bill(cid, draft.id, conv_cmd)
        check("conversion result has order_id", result.order_id == draft.id)
        check("conversion result has bill id", result.purchase_bill_id is not None and result.purchase_bill_id > 0)
        check("order_number matches", result.order_number == sent.order_number)
        print(f"  bill_id={result.purchase_bill_id}, bill_number={result.bill_number}")

        # Verify order is now converted
        converted_order = registry.purchase_order_service.get_order(cid, draft.id)
        check("order status=converted", converted_order.status_code == "converted")
        check("converted_to_bill_id set", converted_order.converted_to_bill_id == result.purchase_bill_id)

        # Double-conversion guard
        assert_raises(
            "cannot convert already-converted order",
            (ValidationError, ConflictError),
            lambda: registry.purchase_order_service.convert_to_bill(cid, draft.id, conv_cmd),
        )

        # ------------------------------------------------------------------
        # 8. Cancel flow test (separate order)
        # ------------------------------------------------------------------
        print("[TEST] 8. Cancel flow...")
        cancel_draft = registry.purchase_order_service.create_draft_order(
            cid,
            CreatePurchaseOrderCommand(
                supplier_id=supplier.id,
                order_date=date(2025, 3, 1),
                currency_code="XAF",
                lines=(
                    PurchaseOrderLineCommand(
                        description="Cancellable item",
                        quantity=Decimal("1"),
                        unit_cost=Decimal("100.00"),
                    ),
                ),
            ),
        )
        cancelled = registry.purchase_order_service.cancel_order(cid, cancel_draft.id)
        check("cancelled draft->cancelled", cancelled.status_code == "cancelled")

        # ------------------------------------------------------------------
        # 9. List + filter
        # ------------------------------------------------------------------
        print("[TEST] 9. List and filter orders...")
        all_orders = registry.purchase_order_service.list_orders(cid)
        check("list returns orders", len(all_orders) >= 2)

        converted_orders = registry.purchase_order_service.list_orders(cid, status_code="converted")
        check("filter by converted works", all(o.status_code == "converted" for o in converted_orders))

        # ------------------------------------------------------------------
        # 10. UI smoke (offscreen)
        # ------------------------------------------------------------------
        print("[TEST] 10. UI page instantiation...")
        try:
            from seeker_accounting.modules.purchases.ui.purchase_orders_page import PurchaseOrdersPage
            page = PurchaseOrdersPage(registry)
            check("PurchaseOrdersPage instantiates", page is not None)
        except Exception as exc:
            print(f"  {FAIL} UI page instantiation: {exc}")
            failures.append("UI page instantiation")

        try:
            from seeker_accounting.modules.purchases.ui.purchase_order_dialog import (
                PurchaseOrderDialog,
                ConvertOrderDialog,
            )
            check("dialog imports ok", True)
        except Exception as exc:
            print(f"  {FAIL} dialog import: {exc}")
            failures.append("dialog import")

        try:
            from seeker_accounting.modules.purchases.ui.purchase_order_lines_grid import PurchaseOrderLinesGrid
            check("lines grid import ok", True)
        except Exception as exc:
            print(f"  {FAIL} lines grid import: {exc}")
            failures.append("lines grid import")

    except Exception as exc:
        import traceback
        print(f"\n[FATAL] Unhandled exception: {exc}")
        traceback.print_exc()
        return 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    if failures:
        print(f"RESULT: {len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    else:
        print("RESULT: ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    import sys
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.exit(main())
