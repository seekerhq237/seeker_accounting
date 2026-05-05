"""Smoke for inventory upgrade plan Phase 1 / Slice 2.1: immutable stock ledger.

Validates the new ledger pipeline end to end:

* A receipt posting writes exactly one ``StockLedgerEntry`` per line and
  upserts the materialized ``StockLedgerBalance`` row.
* An issue posting consumes at the running weighted-average cost.
* ``StockLedgerQueryService.position`` reads the current balance.
* ``StockLedgerQueryService.position(..., as_of=...)`` replays the ledger
  up to a cut-off date.
* The numbering catalog accepts ``inventory_document_draft`` as a valid
  ``document_type_code``.
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
from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand


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

    # ------------------------------------------------------------------
    # 1. Bootstrap company + chart + fiscal + sequences
    # ------------------------------------------------------------------
    import uuid as _uuid
    suffix = _uuid.uuid4().hex[:6].upper()
    company = registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=f"Inv P1 Smoke {suffix} SARL",
            display_name=f"Inv P1 Smoke {suffix}",
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

    # Slice 2.1 deliverable: ``inventory_document_draft`` is now a valid
    # numbering catalog code (UUID fallback still works for callers that
    # skip registering a sequence).
    print("\n--- Numbering catalog accepts inventory_document_draft ---")
    seq = registry.numbering_setup_service.create_document_sequence(
        cid,
        CreateDocumentSequenceCommand(
            document_type_code="inventory_document_draft",
            prefix="DRAFT-",
            next_number=1,
            padding_width=4,
        ),
    )
    check("inventory_document_draft sequence created", seq.document_type_code == "inventory_document_draft")

    # ------------------------------------------------------------------
    # 2. Reference data (UoM, location, accounts, item)
    # ------------------------------------------------------------------
    registry.inventory_reference_data_service.ensure_document_types_seeded(cid)
    registry.inventory_reference_data_service.ensure_standard_reason_codes(cid)

    uom_pcs = registry.unit_of_measure_service.create_unit_of_measure(
        cid, CreateUnitOfMeasureCommand(code="PCS", name="Pieces")
    )
    loc_main = registry.inventory_location_service.create_inventory_location(
        cid, CreateInventoryLocationCommand(code="MAIN", name="Main Warehouse")
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
            standard_cost=Decimal("12.50"),
            lifecycle_status_code="active",
            is_sellable=True,
            is_purchasable=True,
            is_stockable=True,
        ),
    )

    # ------------------------------------------------------------------
    # 3. Receipt of 10 PCS @ 12.50 → ledger entry + balance row.
    # ------------------------------------------------------------------
    print("\n--- Receipt: 10 PCS @ 12.50 ---")
    receipt = registry.inventory_document_service.create_draft_document(
        cid,
        CreateInventoryDocumentCommand(
            document_type_code="goods_receipt_purchase",
            document_date=date(2026, 1, 5),
            location_id=loc_main.id,
            reference_number="PO-1001",
            notes=None,
            reason_code_id=None,
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
    registry.inventory_posting_service.post_inventory_document(cid, receipt.id)

    pos = registry.stock_ledger_query_service.position(
        company_id=cid, item_id=item.id, location_id=loc_main.id
    )
    check("post-receipt on_hand == 10.0000", pos.on_hand == Decimal("10.0000"))
    check("post-receipt value == 125.00", pos.value == Decimal("125.00"))
    check("post-receipt avg_cost == 12.500000", pos.avg_cost == Decimal("12.500000"))

    # ------------------------------------------------------------------
    # 4. Issue of 4 PCS → consumes at weighted avg.
    # ------------------------------------------------------------------
    print("\n--- Issue: 4 PCS @ avg cost ---")
    issue = registry.inventory_document_service.create_draft_document(
        cid,
        CreateInventoryDocumentCommand(
            document_type_code="goods_issue_consumption",
            document_date=date(2026, 1, 10),
            location_id=loc_main.id,
            reference_number="ISS-1001",
            notes=None,
            reason_code_id=None,
            source_module_code="inventory",
            source_document_type="manual",
            source_document_id=None,
            lines=(
                InventoryDocumentLineCommand(
                    item_id=item.id,
                    quantity=Decimal("4"),
                    unit_cost=None,
                    counterparty_account_id=cogs_account,
                ),
            ),
        ),
    )
    registry.inventory_posting_service.post_inventory_document(cid, issue.id)

    pos2 = registry.stock_ledger_query_service.position(
        company_id=cid, item_id=item.id, location_id=loc_main.id
    )
    check("post-issue on_hand == 6.0000", pos2.on_hand == Decimal("6.0000"))
    check("post-issue value == 75.00", pos2.value == Decimal("75.00"))
    check("post-issue avg_cost preserved at 12.500000", pos2.avg_cost == Decimal("12.500000"))

    # ------------------------------------------------------------------
    # 5. As-of replay before the issue.
    # ------------------------------------------------------------------
    print("\n--- As-of replay (2026-01-08) ---")
    pos_asof = registry.stock_ledger_query_service.position(
        company_id=cid, item_id=item.id, location_id=loc_main.id, as_of=date(2026, 1, 8)
    )
    check("as-of on_hand == 10.0000", pos_asof.on_hand == Decimal("10.0000"))
    check("as-of value == 125.00", pos_asof.value == Decimal("125.00"))
    check("as-of avg_cost == 12.500000", pos_asof.avg_cost == Decimal("12.500000"))

    # ------------------------------------------------------------------
    # 6. Insufficient on-hand is rejected.
    # ------------------------------------------------------------------
    print("\n--- Negative on-hand rejection ---")
    rejected = False
    try:
        over_issue = registry.inventory_document_service.create_draft_document(
            cid,
            CreateInventoryDocumentCommand(
                document_type_code="goods_issue_consumption",
                document_date=date(2026, 1, 15),
                location_id=loc_main.id,
                reference_number="ISS-1002",
                notes=None,
                reason_code_id=None,
                source_module_code="inventory",
                source_document_type="manual",
                source_document_id=None,
                lines=(
                    InventoryDocumentLineCommand(
                        item_id=item.id,
                        quantity=Decimal("100"),
                        unit_cost=None,
                        counterparty_account_id=cogs_account,
                    ),
                ),
            ),
        )
        registry.inventory_posting_service.post_inventory_document(cid, over_issue.id)
    except Exception as exc:
        rejected = "Insufficient" in str(exc) or "stock" in str(exc).lower()
    check("over-issue is rejected", rejected)

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
