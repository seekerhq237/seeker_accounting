# Inventory Management Upgrade Plan

Based on the inventory review (sections A–M), this plan delivers a production-grade inventory subsystem aligned with industry-leading ERPs (SAP B1, Sage 100/X3, Odoo, NetSuite, Microsoft BC, QuickBooks Enterprise) and with OHADA / Cameroon SME realities.

The plan is organised as **vertical slices**, each delivering working end-to-end functionality, observable in the UI, posted correctly to GL, and validated. Slices are sequenced so that earlier slices unblock later ones. Nothing in a later slice is required for an earlier slice to ship.

---

## 0. Cross-cutting principles (apply to every slice)

These are non-negotiable and govern every slice below.

1. **Posted accounting truth lives only in journal entries.** Inventory documents and stock ledger entries are the operational record; GL postings are the accounting record. Reports may read from either, but reconciliation between them is a first-class feature, not an afterthought.
2. **Stock truth lives in an immutable stock ledger** (`stock_ledger_entries`), not in mutable cost layers. Cost layers become a derived view of receipts with `quantity_remaining` updated through a separate immutable `cost_layer_consumptions` table.
3. **Per-(company, item, location) is the minimum granularity** for stock-on-hand and cost. No company-wide-only stock query survives.
4. **Quantities are always stored in base UoM** in the stock ledger and cost layers. Transaction UoM and ratio snapshot are kept on documents only for display and for audit.
5. **Monetary precision policy**: Decimal arithmetic in full precision; quantize to 2 decimals only when writing a `*_amount` column or final report value. Quantities to 4 decimals. Costs to 6 decimals internally; 4 on persisted columns. `ROUND_HALF_EVEN` everywhere.
6. **No master-table balance shortcuts.** No `total_value` cached on documents, no `on_hand` on items. All aggregates are queries.
7. **Permissions and period-locks gate every state transition** — at draft, edit, post, void, transfer, count.
8. **All posting is reversible** through explicit reverse-posting workflows that produce a contra journal and contra stock ledger entries. Originals stay immutable.
9. **Pessimistic row locking** on cost layers and on the stock-ledger position row during posting. Optimistic version columns on draft documents.
10. **Service-level enforcement** of company scope, location scope, item type, item state, and UoM-category compatibility. UI is a thin caller.

---

## 1. Phasing overview

| Phase | Theme | Slices |
|---|---|---|
| **P0** | Foundations & data-model correctness | 1.1, 1.2, 1.3, 1.4 |
| **P1** | Stock ledger, multi-location, costing engine | 2.1, 2.2, 2.3, 2.4 |
| **P2** | Sales/purchase integration & COGS automation | 3.1, 3.2, 3.3, 3.4 |
| **P3** | Operational workflows | 4.1, 4.2, 4.3, 4.4 |
| **P4** | Advanced traceability | 5.1, 5.2, 5.3, 5.4 |
| **P5** | Cameroon / OHADA tax & customs alignment | 6.1, 6.2, 6.3 |
| **P6** | Planning, reporting, dashboards, UX polish | 7.1, 7.2, 7.3, 7.4, 7.5 |
| **P7** | Hardening & migration | 8.1, 8.2, 8.3 |

Each slice below specifies: scope, schema changes, services, repositories, DTOs, UI, validation rules, integrations, migration strategy, acceptance criteria, and review-finding mapping.

---

## P0 — Foundations and data-model correctness

### Slice 1.1 — Costing-method discipline and item taxonomy

**Addresses:** I1, I5, B14, C8, F1 (groundwork), F2 (groundwork)

**Scope.** Replace the vestigial per-item cost-method placeholder with a deliberate taxonomy aligned with company preferences and OHADA stock classes.

**Schema.**
- `Item.costing_method_code`: enforced enum at service level — `weighted_average`, `fifo`, `standard_cost`. Default sourced from `CompanyPreferences.default_inventory_cost_method`.
- `Item.standard_cost`: `Numeric(18,6)` nullable; required when `costing_method_code = standard_cost`.
- `Item.lifecycle_status_code`: `active | discontinued | obsolete | draft`. Replaces simple `is_active` semantics for sales/purchase availability.
- `Item.is_sellable`, `Item.is_purchasable`, `Item.is_stockable` booleans (orthogonal to lifecycle).
- `Item.ohada_stock_class_code`: nullable enum — `merchandise(31)`, `raw_material(32)`, `other_consumable(33)`, `in_process(34)`, `finished_goods(35)`, `byproduct(36)`, `packaging(37)`, `in_transit_or_third_party(38)`. Drives default inventory account selection.
- `Item.unit_of_measure_id` becomes `NOT NULL`; remove the denormalized `unit_of_measure_code` column.
- New table `item_account_overrides(company_id, item_id, location_id, inventory_account_id, cogs_account_id, expense_account_id, revenue_account_id)` to support per-location GL accounts.

**Services.**
- `ItemService` validates costing method, lifecycle, and OHADA class consistency.
- `ItemAccountResolverService.resolve_accounts(company_id, item_id, location_id, document_type)` — single source of truth for GL accounts. Used by every posting service.

**Migration.**
- Backfill `costing_method_code` from company preference.
- Backfill `lifecycle_status_code = active` where `is_active`; `discontinued` otherwise.
- Drop `Item.unit_of_measure_code`; update all read paths to use `item.unit_of_measure.code`.

**UI.**
- `ItemDialog` reorganised into tabs: General, Costing & GL, UoM & Conversions, Pricing, Reorder, Tax, Notes.
- Cost-method combo enables the right inputs (standard cost only for `standard_cost`).
- OHADA class combo with helper text describing each class.

**Acceptance.**
- Switching cost method on an item with on-hand stock is blocked with a clear error.
- All items have non-null `unit_of_measure_id` after migration.
- Account resolution prefers per-location override → item default → category default → company default.

---

### Slice 1.2 — Numeric precision policy and rounding service

**Addresses:** C2, C3 (groundwork), C4 (groundwork), C6, I4, I7

**Scope.** A single rounding utility used by all inventory, sales, purchase, and treasury postings.

**Deliverables.**
- `platform/numerics/rounding_policy.py` exposing `quantize_quantity`, `quantize_unit_cost`, `quantize_amount`, all with `ROUND_HALF_EVEN`, configurable per company currency.
- Audit and refactor inventory posting to compute monetary values in full precision and quantize once at journal-line write.
- Remove `InventoryDocument.total_value`; replace with `InventoryDocumentRepository.compute_total_value(doc_id)` and a UI-only `total_value` property on the DTO.
- `InventoryDocumentLine.line_amount` precision becomes `Numeric(18,2)` with NOT NULL after posting.
- Reconciliation invariant test in CI: sum of `quantity_remaining * unit_cost` over cost layers equals the GL `inventory_account` balance for every (company, location).

**Acceptance.** No place in the inventory module quantizes intermediate values mid-formula. Unit tests prove rounding stability across 100k random WAC scenarios.

---

### Slice 1.3 — Per-item UoM matrix and rounding rules

**Addresses:** B12 (partial), C9, C10, I2

**Scope.** Items may declare multiple usable UoMs with conversion direction and rounding rule, beyond the single base UoM.

**Schema.**
- `item_uom_conversions(item_id, uom_id, ratio_to_base Numeric(18,6), is_purchase_default, is_sales_default, is_stocking, rounding_rule_code, min_increment Numeric(18,4))`.
- `rounding_rule_code`: `up | down | nearest | none`.
- DB enforces UoM is in the same `UomCategory` as the item's base UoM (service-validated, not FK-enforced beyond category id).

**Services.**
- `UomConversionService.convert(item_id, qty, from_uom_id, to_uom_id) -> Decimal` honoring rounding rule.
- `InventoryDocumentService` and posting service use this; UoM math is no longer inline.

**Migration.** For each existing item, seed a single conversion row at ratio 1.0 to its base UoM.

**Acceptance.** Mixing UoMs across categories is rejected. Min-increment is enforced when typing quantities.

---

### Slice 1.4 — Document type taxonomy and reason codes

**Addresses:** D1, G3

**Scope.** Replace the three-type model with a richer taxonomy.

**Schema.**
- `inventory_document_types` reference table with codes:
  `goods_receipt_purchase`, `goods_receipt_other`, `goods_issue_sale`, `goods_issue_consumption`, `transfer_out`, `transfer_in`, `transfer_in_transit`, `adjustment_increase`, `adjustment_decrease`, `scrap`, `wastage`, `count_gain`, `count_loss`, `opening_balance`, `production_receipt`, `production_issue`, `customer_return`, `supplier_return`, `revaluation`, `consignment_in`, `consignment_out`.
- `inventory_documents.document_type_code` becomes FK to this table.
- New column `inventory_documents.reason_code_id` → `inventory_reason_codes` (per-company seedable reason taxonomy: `damage, theft, expiry, count_variance, donation, sample, internal_use, obsolescence, revaluation, other`).
- New columns `source_module_code`, `source_document_type`, `source_document_id` to make the traceability graph first-class.

**Services.**
- Each document type has a declarative descriptor: required fields, default GL counterparty role, sign convention, allowed item types, requires-cost flag, requires-batch flag, reverses?, transfers?, project-eligible?
- `InventoryDocumentService` becomes a thin dispatcher over per-type strategies.

**UI.**
- Type-specific dialog templates (extending a common base) instead of one bloated dialog.
- Reason-code combo where the type requires it.

**Acceptance.** Each existing document type maps to one new code via deterministic migration. No business logic uses `document_type_code` string-comparison outside the descriptor table.

---

## P1 — Stock ledger, multi-location, costing engine

### Slice 2.1 — Immutable stock ledger and per-location stock truth

**Addresses:** B5, C1, C5, G1, G7, I8, J, K1

**Scope.** Introduce a single, append-only stock ledger as the canonical operational stock record.

**Schema.**
- New table `stock_ledger_entries`:
  - `id`, `company_id`, `item_id`, `location_id`, `posting_date`, `document_type_code`, `inventory_document_line_id`, `direction (+1/-1)`, `quantity_base`, `unit_cost`, `value`, `running_quantity_after`, `running_value_after`, `running_avg_cost_after`, `created_at`.
  - Indexes on `(company_id, item_id, location_id, posting_date, id)` for as-of queries.
  - Insert-only; updates and deletes blocked by service and DB triggers (where supported by Firebird/Postgres backends; soft-block on SQLite).
- New table `stock_ledger_balances` (materialised current position, optional optimisation):
  - `(company_id, item_id, location_id) PK`, `quantity`, `value`, `avg_cost`, `last_movement_id`, `version`.
  - Optimistic concurrency via `version`. Pessimistic `SELECT … FOR UPDATE` during posting.

**Services.**
- `StockLedgerService.append(...)` is the **only** allowed writer. Used by inventory posting, sales-invoice COGS posting, purchase-bill receipt posting, transfer service, count service, revaluation service.
- `StockLedgerQueryService.position(company_id, item_id, location_id, as_of=None)` returns balance from balances table for current, or replays ledger for as-of.
- Two-phase posting: validate (read-only), then commit (under row-lock on `stock_ledger_balances`).

**Schema fix.** `inventory_cost_layers` gains `location_id NOT NULL`. Migration recreates layers per location from existing receipts (best-effort, with operator-confirmed mapping).

**Acceptance.**
- Two simultaneous posters cannot drive on-hand negative.
- Per-location stock-on-hand exposed in stock view, item detail, item picker.
- Sum of ledger entries per (item, location) equals balances row at all times (CI invariant).

---

### Slice 2.2 — Cost layers v2: immutable consumption log and three real costing methods

**Addresses:** C3, C4, G1, I1

**Scope.** Re-architect costing.

**Schema.**
- `inventory_cost_layers` keeps `quantity_in`, gains `location_id`, gains `is_open` flag.
- New table `cost_layer_consumptions(consumption_id PK, source_layer_id FK, consuming_doc_line_id FK, consumed_quantity, consumed_value, consumed_at, posting_date)` — append-only.
- `quantity_remaining` becomes a **computed view** over `quantity_in - SUM(consumptions)`. Persisted column kept for performance, refreshed atomically inside the same transaction as the consumption insert.

**Services.**
- `WeightedAverageCostingStrategy`: at issue, compute current avg = (sum value / sum qty) for (item, location); post issue at that avg; record consumption proportionally across open layers (oldest-first ordering only for layer bookkeeping). Reconciles GL and ledger to within ±0.01 per posting.
- `FifoCostingStrategy`: at issue, consume layers oldest-first by full unit cost; post value = sum of layer-by-layer consumed value.
- `StandardCostStrategy`: at issue, post at item.standard_cost; post variance to a `purchase_price_variance` GL account on receipt (cost - standard) × qty.

**Selection.** Strategy chosen from `Item.costing_method_code`. Cannot be changed while on-hand > 0 in any location.

**Acceptance.**
- Per-method correctness suite: 1000 randomised receipt/issue scenarios; ledger value ≡ sum of remaining layer values ≡ GL inventory balance.
- Standard-cost variance correctly capitalises into `Variance — Purchase Price` account.

---

### Slice 2.3 — Stock transfers (single document, two ledger sides)

**Addresses:** B4, B5

**Scope.** First-class transfer document with optional in-transit handling.

**Schema.**
- New columns on `inventory_documents`: `from_location_id`, `to_location_id`, `transfer_status_code` (`draft, in_transit, completed, cancelled`).
- `inventory_document_lines` already contain qty; transfer lines never carry unit_cost (cost moves at current avg/FIFO/standard).
- `stock_ledger_entries` produced for transfers: one negative at source, one positive at destination, with optional intermediate "in-transit virtual location" per company.

**Services.**
- `StockTransferService.create_draft`, `dispatch` (issues from source to in-transit), `receive` (closes in-transit at destination), `cancel`, `reverse`.
- GL effect: zero net for direct transfers; for in-transit, debit Class-38 In-Transit, credit source location inventory, then reverse on receipt.

**UI.** Dedicated transfer dialog with from/to combos, an item-picker that shows source-location on-hand, and a "dispatch now" / "receive on arrival" toggle.

**Acceptance.** Multi-warehouse companies can move stock with a single workflow; in-transit appears in stock view as its own pseudo-location with appropriate GL impact.

---

### Slice 2.4 — Reservations, allocations, and ATP

**Addresses:** B6, D9 (groundwork)

**Scope.** Sales orders, jobs, and projects can reserve stock against (item, location). Reservations consume "available" without touching ledger.

**Schema.**
- `stock_reservations(id, company_id, item_id, location_id, quantity, source_module, source_document_id, source_document_line_id, status_code, expires_at, created_at)`.
- Lifecycle: `pending → fulfilled | cancelled | expired`.

**Services.**
- `StockReservationService` with `create`, `release`, `consume_on_issue`.
- `StockLedgerQueryService.position` returns `(on_hand, reserved, on_order, available = on_hand - reserved)`.

**UI.** Stock view and item picker show all four numbers. Sales-order workflow auto-reserves on confirmation, releases on cancellation.

**Acceptance.** ATP = on_hand + on_order – reserved is computed correctly and displayed in real time on the sales order line picker.

---

## P2 — Sales / purchase integration and COGS automation

### Slice 3.1 — `item_id` on sales documents and per-line item enforcement

**Addresses:** B1, B2, B12 (partial)

**Scope.** Add `item_id` to all four sales line tables: quote, order, invoice, credit note. Make it required for stockable items, optional otherwise.

**Schema.**
- `sales_*_lines.item_id` nullable FK initially; service requires it for stockable.
- `sales_*_lines.uom_id`, `sales_*_lines.uom_ratio_snapshot`, `sales_*_lines.base_quantity` (stocking UoM math).
- `sales_*_lines.unit_cost_at_issue`, `sales_*_lines.cogs_amount` (filled by COGS posting).

**Migration.** Existing rows: `item_id = NULL` allowed (one-time exemption); UI distinguishes legacy lines and disallows new lines without item.

**Services.** Sales-line builder validates lifecycle, sellability, UoM, taxability, customer-eligibility (price list).

**Acceptance.** A sales invoice with a stock item now carries the link required by Slice 3.2.

---

### Slice 3.2 — COGS automation on sales invoice posting and customer returns

**Addresses:** B1, B3 (sales side)

**Scope.** When a sales invoice with stockable lines is posted, the system:

1. Resolves location (header default; per-line override allowed).
2. Calls `StockLedgerService` to issue base qty per line at the item's costing method.
3. Posts COGS journal lines: Dr COGS, Cr Inventory, **per location and per OHADA class**, summarised by account.
4. Stores `unit_cost_at_issue` and `cogs_amount` on the sales line for reporting.
5. Cancels reservations originating from the related sales order.

For customer returns (sales credit notes for stock items) the inverse runs: stock returned at the original cost (matched via the credit note's link to the original invoice line), or at current avg if not matched.

**Acceptance.** Gross margin per invoice, per item, per customer, per period is now computable from posted data with no manual adjustment.

---

### Slice 3.3 — `item_id` on purchase documents, GRN workflow, and three-way match

**Addresses:** B1, B3 (purchase side), B11 (groundwork)

**Scope.**
- Add `item_id`, `uom_id`, `uom_ratio_snapshot`, `base_quantity` to PO, bill, supplier credit-note lines.
- Introduce **goods-receipt note (GRN)** as `inventory_documents.document_type_code = goods_receipt_purchase`, with FK chain `purchase_order_line → grn_line → bill_line` for three-way match.
- New table `purchase_order_line_receipt_links` and `purchase_bill_line_receipt_links` to record matched quantities and values.
- New GL behaviour at GRN: Dr Inventory, Cr GRNI (goods received not invoiced) at PO unit cost.
- At bill posting: Dr GRNI, Cr Accounts Payable; price differences post to `Purchase Price Variance`.

**Services.**
- `GoodsReceiptService.create_from_po`, `match_to_bill`, `reverse`.
- Bill-posting service is extended to handle GRN matching.

**Acceptance.**
- Three-way match report (PO vs GRN vs Bill) is exact.
- "Uninvoiced receipts" (GRNI accrual) becomes a queryable balance per period close.
- Standard cost items post PPV correctly.

---

### Slice 3.4 — Item-supplier catalogue, supplier-of-record, last cost, lead time

**Addresses:** B11, B13 (input data), F4 (groundwork)

**Scope.** Multi-supplier item registry.

**Schema.**
- `item_suppliers(id, company_id, item_id, supplier_id, supplier_item_code, supplier_uom_id, last_unit_cost, last_currency_code, last_purchase_date, lead_time_days, is_preferred, minimum_order_qty, price_breaks_json)`.

**Services.** Auto-update `last_unit_cost` and `last_purchase_date` on every posted goods-receipt-from-PO. Manage preferred-supplier flag (only one).

**UI.** New tab on the item dialog "Suppliers"; new column "Preferred supplier" in items list; supplier dropdown on PO line auto-filters to declared suppliers for the item.

**Acceptance.** Reorder workflow (Slice 7.2) can suggest a PO to the preferred supplier with the correct UoM and last-known unit cost.

---

## P3 — Operational workflows

### Slice 4.1 — Reverse posting, void, and edit-after-post controls

**Addresses:** D3, D4, G7

**Scope.**
- `InventoryPostingService.reverse(document_id, reason_code_id, reverse_date)` — posts a reverse stock-ledger entry and a reversing journal in the same fiscal period (or the next open period).
- `cancel_draft_document` requires a reason code, soft-deletes orphan lines.
- Posted documents become read-only; "Reverse" replaces "Edit" in the document register.
- Cost-layer consumptions are inserted as positive consumption-reversal records, never updated.

**Acceptance.** Mistakes are correctable without breaking immutability invariants. Audit trail shows "doc X posted, doc Y reversed X" with reason code and approver.

---

### Slice 4.2 — Maker-checker for posting; posting queue

**Addresses:** D7, G4

**Scope.**
- Permission split: `inventory.documents.create_draft`, `inventory.documents.edit_draft`, `inventory.documents.cancel_draft`, `inventory.documents.submit_for_posting`, `inventory.documents.post`, `inventory.documents.reverse`.
- New status `pending_posting` between `draft` and `posted`. The same user cannot both submit and post a document if `enforce_segregation_of_duties` is true on company preferences.
- New "Posting Queue" page listing `pending_posting` documents.

**Acceptance.** Configurable SoD; auditor-friendly approval trail.

---

### Slice 4.3 — Stock count workflow v2 (plan, freeze, count, recount, approve, post)

**Addresses:** D5, D6, E5, G3

**Scope.**
- New entities: `stock_count_plan`, `stock_count_session`, `stock_count_line`, `stock_count_recount`, `stock_count_variance`.
- Phases: Plan (locations, item filter, cycle-class) → Freeze (snapshots system on-hand per (item, location)) → Count (entered counts) → Recount (optional, item-by-item) → Variance review (with reasons) → Approve → Post (single adjustment_increase + adjustment_decrease document per location per session).
- Printable count sheets and put-away sheets per location.
- Cycle-count plans by ABC class with frequency.

**Acceptance.** Original counted quantities and snapshots remain queryable indefinitely after posting.

---

### Slice 4.4 — Bulk import / templates

**Addresses:** D12

**Scope.**
- CSV/XLSX templates for: items, item categories, UoMs, item-suppliers, opening balances, price lists, BOMs (P4).
- Two-phase import: validate-and-preview, then apply.
- Templates ship in `artifacts/templates/inventory/`.
- Import jobs persisted in existing `import_jobs` infrastructure.

**Acceptance.** A new company can be onboarded with hundreds of items in minutes; preview catches all conflicts before any write.

---

## P4 — Advanced traceability

### Slice 5.1 — Batch / lot tracking with FEFO

**Addresses:** B7

**Scope.**
- `Item.tracking_mode_code`: `none | batch | serial`.
- New tables `item_batches(id, company_id, item_id, batch_number, manufactured_on, expiry_on, supplier_id)`.
- `inventory_document_lines.batch_id` (when tracking=batch).
- `stock_ledger_entries.batch_id`.
- Cost layers tied to (item, location, batch).
- `FEFO` strategy added when `Item.consumption_strategy = fefo`.

**UI.** Batch picker on issue when item is batch-tracked; expiry warnings; FEFO suggestion.

**Acceptance.** Batch-controlled item movements are traceable end-to-end. Expired-stock report works.

---

### Slice 5.2 — Serial number tracking

**Addresses:** B7

**Scope.**
- `item_serials(id, item_id, serial_number, status_code, current_location_id, current_doc_line_id, warranty_until, ...)`.
- `inventory_document_lines.serial_ids` via M2M `inventory_document_line_serials`.
- Receipts allocate new serials; issues consume named serials; transfers move serials.
- Hooks for warranty/service module (out of scope).

**Acceptance.** A serialized item's full history is reconstructable from its serial id alone.

---

### Slice 5.3 — Item variants / matrix items

**Addresses:** B8

**Scope.**
- `item_attribute_definitions` (size, colour, …) per category.
- `item_variants(parent_item_id, attribute_value_combination_hash, child_item_id)`.
- A variant is itself a regular `Item` with its own SKU, costed independently. Parent items are non-stockable.

**UI.** Matrix entry grid for receipts and price lists.

**Acceptance.** Apparel/retail use cases can be modeled.

---

### Slice 5.4 — Bills of materials, kits, assemblies

**Addresses:** B9

**Scope.**
- `bills_of_material(item_id, version, status_code, effective_from, effective_to, type_code: kit|assembly|service_kit)`.
- `bom_components(bom_id, component_item_id, quantity_per, scrap_percent, uom_id)`.
- `production_orders` and `production_order_lines` (lightweight; full MRP out of scope).
- Posting: production receipt + production issue, valued at component cost + optional fixed labour overhead.
- Kits at sale: explode into components for stock movement; single revenue line.

**Acceptance.** Simple food-service / kit-retail / light-manufacturing scenarios work end-to-end.

---

## P5 — Cameroon / OHADA tax and customs alignment

### Slice 6.1 — VAT-into-cost, non-deductible input VAT, exempt items

**Addresses:** F1

**Scope.**
- `Item.is_vat_exempt_sales`, `Item.is_vat_exempt_purchases` (override of tax codes).
- Purchase posting: when the tax code is non-deductible (or partially non-deductible), the non-deductible portion is **capitalised into the goods-receipt unit cost** before cost-layer creation.
- Reporting: input VAT recovered vs capitalised, per period.

**Acceptance.** Correct OHADA / Cameroon DGI handling of exempt-output activities buying VATed inputs.

---

### Slice 6.2 — Landed cost, customs declaration, multi-currency receipts

**Addresses:** B10, F4, F5

**Scope.**
- New entity `landed_cost_voucher(id, company_id, declaration_number, total_freight, total_duty, total_insurance, total_other, allocation_basis_code: by_value|by_qty|by_weight|manual)`.
- Each voucher allocates costs to one or more goods-receipts and increases their cost layers via `revaluation` ledger entries.
- `inventory_documents.foreign_currency_code` and `foreign_currency_amount` for receipts; FX rate at receipt date determines functional-currency unit cost; cost layers persist functional cost only.
- New column `inventory_documents.customs_declaration_number`, `bill_of_lading_number`, `port_entry_date`, linkable to a future imports module.

**Acceptance.** A typical Cameroonian import scenario (FOB cost in EUR, freight in EUR, duty in XAF, port fees in XAF, declaration stamp) produces correct landed cost on every cost layer.

---

### Slice 6.3 — OHADA Class 3 sub-account behaviour and `livre d'inventaire`

**Addresses:** F2, F3

**Scope.**
- Default chart-of-accounts seed maps each `ohada_stock_class_code` to its class-3 sub-account (31x merchandise, 32x raw materials, 33x other consumables, 34x in-process, 35x finished goods, 36x by-products, 37x packaging, 38x in-transit, 39x impairment provisions).
- Year-end "variation de stocks" service computes opening - closing for each class and posts the standard SYSCOHADA entries (60_3xx vs 31x, 71/72/73 vs 33-37 etc.).
- Stock impairment workflow: post to 39x without touching cost layers (provision at GL only); reversed on next valuation.
- `Livre d'inventaire` printable report: opening balance per item per location, all movements in the period, closing balance, with company seal block and signature lines.

**Acceptance.** OHADA financial statements show correct stock movements line; auditor can be handed a `livre d'inventaire` PDF directly.

---

## P6 — Planning, reporting, dashboards, UX polish

### Slice 7.1 — Price lists and customer-specific pricing

**Addresses:** B12

**Scope.**
- `price_lists`, `price_list_lines(item_id, uom_id, currency_code, valid_from, valid_to, price, qty_break_min)`.
- `customers.price_list_id`, `customer_groups.price_list_id`.
- Sales line auto-prices by hierarchy: customer → group → company default → item list price.

**UI.** Price-list editor, price-history per item, "what-would-this-customer-pay" preview on the item picker.

---

### Slice 7.2 — Reorder, planning, suggested PO

**Addresses:** B13, D10

**Scope.**
- Per `(item, location)` reorder profile: `min_qty`, `max_qty`, `safety_stock`, `lead_time_override_days`.
- Planning service computes suggestions: `available + on_order < min` → suggest PO of `(max - available)` to preferred supplier, in supplier's purchase UoM.
- Output: suggested-PO list; user can accept all, accept some, edit, then "Generate POs".
- Notification subscriptions: low stock, expiring batches, ageing draft documents, posting-queue backlog.

---

### Slice 7.3 — Reporting suite

**Addresses:** E1, E2, E3, E4

**New / fixed reports.**
- Stock-on-hand by location (NEW).
- Stock valuation as-of-date (FIX C1, E2, E3) — sourced from stock ledger, not from documents-with-sign.
- Kardex / item ledger card per (item, location).
- Inventory ageing (NEW).
- ABC analysis (NEW) — Pareto on annual COGS.
- Slow-moving / dead stock report (NEW).
- Days-of-stock / days-of-cover (NEW).
- Item profitability (gross margin) by item / category / customer / period (NEW; needs Slice 3.x).
- Negative-stock attempts log (NEW).
- Batch / lot expiry exposure (NEW).
- Open POs vs on-hand vs reorder (NEW).
- GRNI accrual (NEW).
- Inventory-to-GL reconciliation report (NEW).
- Cost-layer detail per item (NEW).
- Standard-cost vs actual variance (NEW).
- Stock-count variance archive (NEW).
- Livre d'inventaire (Slice 6.3).

All reports respect company scope, fiscal period, location filter, item-category filter, and as-of-date.

---

### Slice 7.4 — Inventory dashboard and shell polish

**Addresses:** H1, H3, H5, D11

**Scope.**
- New "Inventory Overview" page: KPI tiles (total value, # items below reorder, expiring within 30 days, ageing > 180 days, GRNI balance, draft-doc backlog, top-5 movers, top-5 slow movers).
- Stock view gains location, category, value-band, status filters; export to CSV/XLSX.
- Items list adds inline columns: on-hand (preferred location), available, last cost, last sale price, lifecycle status. Each is a derived column with caching.
- Item picker dialog used everywhere: shows on-hand per location, last cost, sellable/purchasable flags, batches/serials when applicable.

---

### Slice 7.5 — Barcode and scanner-friendly entry

**Addresses:** E6, H4

**Scope.**
- `Item.barcode` + `item_barcodes` table for multiple GTINs/EANs/UPCs.
- Document line entry supports scanner input: scanned code resolves item; quantity auto-increments; ENTER moves to next line.
- Stock-count tablet-like UI mode (single-line input, big numbers, recent scans list).
- Pick-list and put-away printables.

---

## P7 — Hardening and migration

### Slice 8.1 — Concurrency, locking, and consistency invariants

**Addresses:** C4, J, K1, K2

**Scope.**
- Pessimistic row-locking on `stock_ledger_balances` during posting (per item, location).
- Optimistic `version` column on `inventory_documents`; UI passes back the version on save/post.
- Background invariant checker (scheduled job + on-demand): for every (company, item, location), `sum(ledger.qty * direction) == balances.quantity` and `sum(layer.remaining * unit_cost) == ledger value` and inventory GL trial balance == sum of ledger value. Discrepancies are surfaced on a "System Health" page.
- Database constraints (where supported): `CHECK (quantity >= 0)` on `stock_ledger_balances.quantity`.

---

### Slice 8.2 — Data migration of existing inventory data

**Scope.**
- Migration plan executes in this order, idempotently:
  1. Populate `item.unit_of_measure_id` where missing; drop denormalized code.
  2. Backfill new enums (lifecycle, OHADA class, costing method, sellable/purchasable/stockable).
  3. Build `stock_ledger_entries` from the entire history of posted `inventory_documents` in chronological order.
  4. Build `inventory_cost_layers` v2 with `location_id` (assigning to header location; if header location null, assign to a "Main" default created per company).
  5. Compute `stock_ledger_balances`.
  6. Reconcile GL inventory account against rebuilt ledger; differences land in a `Migration Variance` GL account that the user must clear.
  7. Backfill `item_id = NULL` on legacy sales/purchase lines and freeze them as legacy.
- A migration report is produced per company: rows touched, variances surfaced, items requiring mapping.

**Acceptance.** Migration on the largest customer dataset completes without data loss; variances are explicit, never silent.

---

### Slice 8.3 — Test, smoke, and acceptance harness

**Scope.**
- Unit tests per costing strategy (1k randomised scenarios each, deterministic seed).
- Property tests: ledger ≡ balances; ledger value ≡ GL inventory balance; total qty ≥ 0 always.
- Integration smokes: full sales cycle (quote → SO → reservation → invoice → COGS → return → reversal); full purchase cycle (PO → GRN → bill → landed cost → cost layer); transfer (with and without in-transit); count workflow; revaluation; year-end variation de stocks.
- UI smokes: item dialog, document dialogs per type, stock view filters, item picker performance with 10k items.
- Performance: posting 1k-line invoice in < 2 s; stock view of 10k items in < 1 s.

---

## Sequencing rationale and gating

- **P0** must land first — every later slice depends on the precision policy, document-type taxonomy, and item taxonomy.
- **P1** is the "spine" upgrade. Once shipped, the system has correct stock truth even before sales/purchase integration.
- **P2** turns the system from "inventory side-app" into a real subledger that drives COGS automatically. From here on, gross margin and item profitability are real.
- **P3** brings operational maturity: reversals, segregation of duties, modern stock counts, bulk import.
- **P4** broadens addressable market (pharmacy, food, retail, light manufacturing).
- **P5** delivers the OHADA / Cameroon-specific value that differentiates the product locally.
- **P6** turns the foundation into a polished product.
- **P7** locks in correctness for production rollouts.

Each slice is independently shippable behind a feature flag where reasonable (`features.stock_ledger_v2`, `features.cogs_automation`, `features.batch_tracking`, …) so the modular monolith continues to behave predictably while migration progresses.

---

## Mapping back to review findings

| Finding | Slice(s) |
|---|---|
| B1 sales/purchase disconnected | 3.1, 3.2, 3.3 |
| B2 no item analytics | 3.1, 3.2, 7.3 |
| B3 no GRN | 3.3 |
| B4 no transfers | 2.3 |
| B5 layers not location-aware | 2.1, 2.2 |
| B6 no reservations / ATP | 2.4 |
| B7 no batch/lot/serial/expiry | 5.1, 5.2 |
| B8 no variants | 5.3 |
| B9 no BOM | 5.4 |
| B10 no landed cost | 6.2 |
| B11 no item-supplier | 3.4 |
| B12 no price lists | 7.1 |
| B13 no reorder engine | 7.2 |
| B14 item lifecycle | 1.1 |
| B15 no document linkage | 1.4, 3.2, 3.3 |
| C1 two stock truths | 2.1, 7.3 |
| C2 wrong unit-cost direction | 1.2 |
| C3 WAC drift | 2.2 |
| C4 GL ↔ ledger reconciliation | 2.2, 8.1 |
| C5 negative stock per location | 2.1 |
| C6 rounding | 1.2 |
| C7 total_value semantics | 1.2 |
| C8 unit_of_measure_code denorm | 1.1 |
| C9, C10 UoM matrix | 1.3 |
| D1 thin doc types | 1.4 |
| D2 random draft numbers | 4.1 |
| D3 cancel semantics | 4.1 |
| D4 no reverse posting | 4.1 |
| D5 stock count workflow | 4.3 |
| D6 single location per doc | 2.3, 4.3 |
| D7 no maker-checker | 4.2 |
| D8 mixed item types | 1.4 |
| D9 project consumption rigor | 2.4, 3.2 |
| D10 alerts | 7.2 |
| D11 stock-on-hand inline | 7.4 |
| D12 bulk import | 4.4 |
| E1–E5 reporting | 7.3 |
| E6 barcode | 7.5 |
| F1 VAT into cost | 6.1 |
| F2 OHADA Class 3 | 6.3 |
| F3 livre d'inventaire | 6.3 |
| F4 multi-currency | 6.2 |
| F5 customs | 6.2 |
| G1 mutable layers | 2.2 |
| G2 audit drops | 8.3 |
| G3 reason codes | 1.4 |
| G4 permissions | 4.2 |
| G5 fiscal-period gate at draft | 4.1 |
| G6 cost-layer reference protection | 2.2, 8.1 |
| G7 tamper evidence | 2.1, 4.1 |
| H1 fragmented shell | 7.4 |
| H2 generic doc dialog | 1.4 |
| H3 item picker | 7.4 |
| H4 grid editing | 7.5 |
| H5 stock view filters | 7.4 |
| I1 cost method enum | 1.1, 2.2 |
| I2 cross-company UoM | 1.3 |
| I3 nullable line_amount | 1.2 |
| I4 precision asymmetry | 1.2 |
| I5 nullable item.UoM | 1.1 |
| I6 created_by_user_id | 4.1 |
| I7 total_value cache | 1.2 |
| I8 reorder per location | 7.2 |
| J negative stock check | 2.1, 8.1 |
| K1, K2 concurrency | 2.1, 8.1 |
| L Tier-1/2/3 | covered in aggregate |

---

## What this plan does not promise

- A full MRP/MPS engine. Production is intentionally a lightweight slice (5.4); deeper manufacturing is a separate product line.
- WMS-grade put-away algorithms, slot-level bin tracking, conveyor integrations.
- Direct integration with Cameroonian customs portals or DGI e-filing — those depend on third-party APIs and stay out of this scope per CLAUDE.md.
- Mobile/handheld scanner clients — the desktop barcode entry path (Slice 7.5) is the bridge until a separate mobile slice is approved.

---

## Definition of "done" for the whole upgrade

1. Every review finding (A–M) maps to a closed slice, validated by automated tests and at least one smoke script.
2. Every numerical invariant in §0 is enforced by a CI check.
3. The accounting team can execute a full month-end close on a multi-warehouse, multi-currency company with batch-tracked items, and produce: balance sheet, income statement (with correct COGS), stock valuation report, kardex per item, livre d'inventaire — all reconciling to the GL within the company's rounding tolerance.
4. The implementation never violates the architectural rules in CLAUDE.md: UI never writes the ledger, services own posting, repositories stay query-shaped, models stay persistence-shaped, no master-table balance shortcuts, no skipped period locks, no posted-document mutation in normal flow.
