"""
Slice 11a: Sales Orders -- Workflow Smoke Test

Validates end-to-end SO workflow:
1. Setup: Company, chart, fiscal year, sequences, customer, tax, accounts
2. Draft SO creation and update
3. Status flow: draft -> confirmed
4. Cancellation guards
5. Conversion: confirmed -> sales invoice
6. Double-conversion guard
7. Cancel flow (separate order)
8. List + filter
9. UI page navigation (offscreen)
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtWidgets import QApplication

from shared.bootstrap import bootstrap_script_runtime
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
from seeker_accounting.modules.customers.dto.customer_commands import (
    CreateCustomerCommand,
    CreateCustomerGroupCommand,
)
from seeker_accounting.modules.sales.dto.sales_order_commands import (
    ConvertSalesOrderCommand,
    CreateSalesOrderCommand,
    SalesOrderLineCommand,
    UpdateSalesOrderCommand,
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
                legal_name=f"SO Smoke {timestamp} SARL",
                display_name="SO Smoke",
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

        try:
            accounts = registry.chart_of_accounts_service.list_accounts(cid)
        except Exception:
            accounts = []
        print(f"  {PASS} accounts loaded: {len(accounts)}")

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

        # Sales invoice sequence
        registry.numbering_setup_service.create_document_sequence(
            cid,
            CreateDocumentSequenceCommand(
                document_type_code="sales_invoice",
                prefix="INV-",
                next_number=1,
                padding_width=6,
            ),
        )
        print(f"  {PASS} invoice numbering sequence")

        # ------------------------------------------------------------------
        # 2. Customer
        # ------------------------------------------------------------------
        print("[TEST] 2. Creating customer...")
        cg = registry.customer_service.create_customer_group(
            cid, CreateCustomerGroupCommand(code="RETAIL", name="Retail Customers")
        )
        customer = registry.customer_service.create_customer(
            cid,
            CreateCustomerCommand(
                customer_group_id=cg.id,
                customer_code="CUST001",
                display_name="Test Customer Ltd",
                payment_term_id=term.id,
            ),
        )
        print(f"  {PASS} customer {customer.id} created")

        # Tax code (zero rate — keeps conversion simple)
        tax_code = registry.tax_setup_service.create_tax_code(
            cid,
            CreateTaxCodeCommand(
                code="ZERO",
                name="Zero Rate",
                rate_percent=Decimal("0.00"),
                tax_type_code="sales",
                calculation_method_code="standard",
                effective_from=date(2025, 1, 1),
            ),
        )
        print(f"  {PASS} tax code {tax_code.code}")

        # Revenue account
        revenue_account = next(
            (a for a in accounts if a.allow_manual_posting and "revenue" in (a.account_name or "").lower()),
            accounts[0] if accounts else None,
        )
        print(f"  {PASS} revenue account {revenue_account.id if revenue_account else 'N/A'}")

        # ------------------------------------------------------------------
        # 3. Create draft SO
        # ------------------------------------------------------------------
        print("[TEST] 3. Create draft SO...")

        line1 = SalesOrderLineCommand(
            description="Consulting Services",
            quantity=Decimal("10"),
            unit_price=Decimal("50000.00"),
            discount_percent=None,
            tax_code_id=None,
            revenue_account_id=revenue_account.id if revenue_account else None,
        )
        line2 = SalesOrderLineCommand(
            description="Support Retainer",
            quantity=Decimal("1"),
            unit_price=Decimal("200000.00"),
            discount_percent=None,
            tax_code_id=None,
            revenue_account_id=None,
        )

        cmd_create = CreateSalesOrderCommand(
            customer_id=customer.id,
            order_date=date(2025, 3, 15),
            requested_delivery_date=date(2025, 3, 30),
            currency_code="XAF",
            reference_number="CUST-PO-001",
            notes="Priority order",
            lines=(line1, line2),
        )
        draft = registry.sales_order_service.create_draft_order(cid, cmd_create)
        check("draft order created", draft is not None)
        check("order_number starts with SO-DRAFT-", draft.order_number.startswith("SO-DRAFT-"))
        check("status is draft", draft.status_code == "draft")
        check("subtotal correct", draft.subtotal_amount == Decimal("700000.00"))
        check("2 lines", len(draft.lines) == 2)
        print(f"  order_number={draft.order_number}, subtotal={draft.subtotal_amount}")

        # ------------------------------------------------------------------
        # 4. Update draft SO
        # ------------------------------------------------------------------
        print("[TEST] 4. Update draft SO...")
        cmd_update = UpdateSalesOrderCommand(
            customer_id=customer.id,
            order_date=date(2025, 3, 16),
            requested_delivery_date=None,
            currency_code="XAF",
            reference_number="CUST-PO-001-REV",
            notes="Updated notes",
            lines=(
                SalesOrderLineCommand(
                    description="Consulting Services Revised",
                    quantity=Decimal("12"),
                    unit_price=Decimal("50000.00"),
                    revenue_account_id=revenue_account.id if revenue_account else None,
                ),
            ),
        )
        updated = registry.sales_order_service.update_draft_order(cid, draft.id, cmd_update)
        check("order updated", updated is not None)
        check("still draft", updated.status_code == "draft")
        check("1 line", len(updated.lines) == 1)
        check("line description updated", updated.lines[0].description == "Consulting Services Revised")
        check("subtotal updated", updated.subtotal_amount == Decimal("600000.00"))

        # ------------------------------------------------------------------
        # 5. Confirm order (draft -> confirmed)
        # ------------------------------------------------------------------
        print("[TEST] 5. Confirm order...")
        confirmed = registry.sales_order_service.confirm_order(cid, draft.id)
        check("status is confirmed", confirmed.status_code == "confirmed")
        check("order_number finalised (SO-)", confirmed.order_number.startswith("SO-") and not confirmed.order_number.startswith("SO-DRAFT-"))
        print(f"  finalised number={confirmed.order_number}")

        # Cannot update confirmed order
        assert_raises(
            "cannot update confirmed order",
            ValidationError,
            lambda: registry.sales_order_service.update_draft_order(cid, draft.id, cmd_update),
        )

        # ------------------------------------------------------------------
        # 6. Convert to invoice (confirmed -> invoiced)
        # ------------------------------------------------------------------
        print("[TEST] 6. Convert to invoice...")
        conv_cmd = ConvertSalesOrderCommand(
            invoice_date=date(2025, 3, 20),
            due_date=date(2025, 4, 20),
            reference_number="INV-FROM-SO",
            notes="Converted from SO",
        )
        result = registry.sales_order_service.convert_to_invoice(cid, draft.id, conv_cmd)
        check("conversion result has order_id", result.order_id == draft.id)
        check("conversion result has invoice id", result.invoice_id is not None and result.invoice_id > 0)
        check("order_number matches", result.order_number == confirmed.order_number)
        print(f"  invoice_id={result.invoice_id}")

        # Verify order is now invoiced
        invoiced_order = registry.sales_order_service.get_order(cid, draft.id)
        check("order status=invoiced", invoiced_order.status_code == "invoiced")
        check("converted_to_invoice_id set", invoiced_order.converted_to_invoice_id == result.invoice_id)

        # Double-conversion guard
        assert_raises(
            "cannot convert already-invoiced order",
            (ValidationError, ConflictError),
            lambda: registry.sales_order_service.convert_to_invoice(cid, draft.id, conv_cmd),
        )

        # ------------------------------------------------------------------
        # 7. Cancel flow test (separate order)
        # ------------------------------------------------------------------
        print("[TEST] 7. Cancel flow...")
        cancel_draft = registry.sales_order_service.create_draft_order(
            cid,
            CreateSalesOrderCommand(
                customer_id=customer.id,
                order_date=date(2025, 3, 1),
                currency_code="XAF",
                lines=(
                    SalesOrderLineCommand(
                        description="Cancellable service",
                        quantity=Decimal("1"),
                        unit_price=Decimal("10000.00"),
                    ),
                ),
            ),
        )
        cancelled = registry.sales_order_service.cancel_order(cid, cancel_draft.id)
        check("cancelled draft->cancelled", cancelled.status_code == "cancelled")

        # Confirm a separate order then cancel it
        confirm_then_cancel = registry.sales_order_service.create_draft_order(
            cid,
            CreateSalesOrderCommand(
                customer_id=customer.id,
                order_date=date(2025, 3, 1),
                currency_code="XAF",
                lines=(
                    SalesOrderLineCommand(
                        description="Another service",
                        quantity=Decimal("2"),
                        unit_price=Decimal("5000.00"),
                    ),
                ),
            ),
        )
        registry.sales_order_service.confirm_order(cid, confirm_then_cancel.id)
        confirm_cancel_result = registry.sales_order_service.cancel_order(cid, confirm_then_cancel.id)
        check("cancelled confirmed->cancelled", confirm_cancel_result.status_code == "cancelled")

        # ------------------------------------------------------------------
        # 8. List + filter
        # ------------------------------------------------------------------
        print("[TEST] 8. List and filter orders...")
        all_orders = registry.sales_order_service.list_orders(cid)
        check("list returns orders", len(all_orders) >= 3)

        invoiced_orders = registry.sales_order_service.list_orders(cid, status_code="invoiced")
        check("filter by invoiced works", all(o.status_code == "invoiced" for o in invoiced_orders))

        # ------------------------------------------------------------------
        # 9. UI smoke (offscreen)
        # ------------------------------------------------------------------
        print("[TEST] 9. UI page instantiation...")
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        try:
            from seeker_accounting.modules.sales.ui.sales_orders_page import SalesOrdersPage
            page = SalesOrdersPage(registry)
            check("SalesOrdersPage instantiates", page is not None)
        except Exception as exc:
            print(f"  {FAIL} UI page instantiation: {exc}")
            failures.append("UI page instantiation")

        try:
            from seeker_accounting.modules.sales.ui.sales_order_dialog import (
                SalesOrderDialog,
                ConvertSalesOrderDialog,
            )
            check("dialog imports ok", True)
        except Exception as exc:
            print(f"  {FAIL} dialog import: {exc}")
            failures.append("dialog import")

        try:
            from seeker_accounting.modules.sales.ui.sales_order_lines_grid import SalesOrderLinesGrid
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
        print("RESULT: All checks passed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
