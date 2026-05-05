# VAT Module â€” Comprehensive Remediation & Upgrade Plan

Plan organised as **vertical slices** consistent with the existing T-series taxation slices. Each slice is independently shippable, validated, and reversible. Phases are dependency-ordered: phase N+1 requires phase N's data model.

Estimated total: **15 slices** across **5 phases**. No phase ships without green tests + smoke + Alembic round-trip.

---

## PHASE A â€” Correctness foundation (single source of truth)

This phase fixes the computational bombs before adding any feature. Nothing else lands until A is green.

---

### Slice T29 â€” Unified VAT aggregator on `posted_tax_lines`
**Problem fixed:** Â§1.1 (two divergent sources of truth â€” credit notes silently excluded from returns).

**Scope**
- Replace `_compute_vat_box_totals` in `tax_return_service.py` with delegation to `PostedTaxLineRepository.aggregate_for_period(...)`.
- Aggregator becomes single-sourced: same fact table that `tax_settlement_service.py` already uses.
- Sales credit notes and purchase credit notes (already writing signed-negative facts via `tax_fact_service.py`) automatically flow into the return.

**Touch list**
- `services/tax_return_service.py` â€” drop direct `SalesInvoice` / `PurchaseBill` joins; rewrite `_compute_vat_box_totals` to call `posted_tax_line_repository_factory` + `fiscal_period_repository_factory`.
- `factories.py` â€” inject `posted_tax_line_repository_factory` + `fiscal_period_repository_factory` into `TaxReturnService`.
- `service_registry.py` â€” no shape change.
- Constants â€” keep the 6 internal box codes as bridge layer for now; T30 replaces them.

**Validation**
- New tests in `tests/test_slice_t29_unified_vat_aggregator.py`:
  - sales invoice + sales credit note in same period â‡’ net taxable_sales / output_vat
  - purchase bill + purchase credit note â‡’ net taxable_purchases / input_deductible
  - non-recoverable input VAT routes to `INPUT_TAX_NON_DEDUCTIBLE` only
  - settlement preview vs draft return reconcile penny-for-penny on synthetic dataset (the regression guard for Â§1.1)
- Existing 600 tests must still pass; `tests/test_slice_t4_tax_compliance.py` may need fixture adjustments.

**Acceptance**
- A drafted return for a period containing both invoices and credit notes shows the **same** output VAT figure as the settlement-preview total. Reconciliation gap = 0.

---

### Slice T30 â€” Wire `tax_codes.return_box_code` and `exemption_kind` into aggregation
**Problem fixed:** Â§1.3 (`return_box_code` column dead) + the form-line breakdown gap (Â§3 L18-L29).

**Scope**
- Aggregator now groups by `posted_tax_lines.tax_code_id` and looks up `tax_code.return_box_code` + `tax_code.exemption_kind` to bucket facts into the **statutory line codes** (L17, L18, L19, L20, L21, L22, L26, L27, L28, L29, L46) directly.
- Replace the 6-box internal scheme with a richer set: bucket map = `RETURN_BOX_CODE â†’ DGI line code`, with L23/L30/L36/L40/L41/L43/L47 computed totals.
- Persisted `tax_return_lines` now carry the **statutory line code** (`L17` etc.) as `box_code`. Migration backfills existing rows by mapping `TAXABLE_SALES â†’ L17` etc.
- `vat_return_form_layout.py` becomes a near-pass-through: indexes by L-code, populates totals.
- `exemption_kind` drives L21 (EXPORT) / L22 (EXEMPT) / L29 (foreign services if `is_imported_service`).

**Touch list**
- New constants: `VAT_RETURN_LINE_L17` â€¦ `L47` in `taxation/constants/__init__.py`.
- New mapping table on `tax_codes`: requires a small migration to add `is_imported_service: bool` and `is_export: bool` flags, since `exemption_kind=EXPORT` is partly orthogonal.
- `services/tax_return_service.py` â€” `_compute_vat_box_totals` becomes `_compute_vat_form_lines` returning `dict[str, dict[str, Decimal]]` (line_code â†’ {base, tax}).
- `services/vat_return_form_layout.py` â€” read straight from line_code keyed lines, drop the bridge layer.
- Migration `aXXb...` adds the two columns to `tax_codes` (nullable, default false).
- Seed/wizard: update VAT-19.25 to set `return_box_code='L17'`, VAT-EXPORT to `is_export=True / return_box_code='L21'`, VAT-EXEMPT to `exemption_kind='EXEMPT' / return_box_code='L22'`, etc.

**Validation**
- New `tests/test_slice_t30_per_line_aggregation.py`: 7+ tax-code variants verify each lands in the correct DGI line.
- Existing snapshot test for PDF rendering updated to assert L18/L21/L22 populated when relevant.

**Acceptance**
- A VAT return covering exports, exempt sales, standard-rate sales, and standard-rate purchases populates **L17, L21, L22, L26, L30, L36, L40, L47** with correct values; L18-L20/L27-L29 populate when corresponding tax codes exist.

---

### Slice T31 â€” Tax-point date as first-class field
**Problem fixed:** Â§1.2 (period filter uses invoice/bill date, not tax point).

**Scope**
- Add nullable `tax_point_date: date` to: `sales_invoices`, `sales_credit_notes`, `purchase_bills`, `purchase_credit_notes`. Default behaviour: `tax_point_date = invoice_date` when null (back-compat).
- Add `tax_point_date` to `posted_tax_lines` and stamp it at posting time.
- `tax_fact_service.py` accepts `tax_point_date` from caller.
- `posted_tax_line_repository.aggregate_for_period(...)` filters by `tax_point_date` (not `posted_at`/document date) when present, falling back to document date when null.
- UI: dialogs for invoices / bills add an optional "Tax point date" field (collapsed by default; visible only when company tax profile flags `vat_uses_tax_point=True`).
- Add `vat_uses_tax_point: bool` to `CompanyTaxProfile`.

**Touch list**
- 4 migrations rolled into one: `aXXcâ€¦_tax_point_date.py` (additive nullable column, no backfill needed, defaults via service).
- 4 service updates (sales invoice / sales credit note / purchase bill / purchase credit note posting services).
- 4 dialogs / UI tweaks.
- New seed/scaffold value `vat_uses_tax_point` defaults to False to preserve current behaviour.

**Validation**
- `tests/test_slice_t31_tax_point.py`: an invoice dated 31-March with `tax_point_date=2-April` lands in the April return, not March.
- Round-trip Alembic.

**Acceptance**
- Service businesses can now configure cash-basis VAT (next slice activates it) without schema changes.

---

### Slice T32 â€” Cash-basis VAT scheme
**Problem fixed:** Â§1.2 cont., Â§1.10 (withholding integration baseline).

**Scope**
- `CompanyTaxProfile` gains `vat_scheme_code: str` âˆˆ {`ACCRUAL`, `CASH`, `MIXED`}, default `ACCRUAL`.
- Under `CASH` regime, the posting services compute `tax_point_date` automatically from the **first allocated payment date** (sales) or **first paid-out date** (purchases) instead of document date.
- New `vat_cash_basis_recompute_service.py` â€” given a payment posted today, finds invoices whose `tax_point_date IS NULL` (cash regime) and stamps them when allocation reaches 100% (or pro-rata for partial). Triggered from the existing payment-allocation services.
- Edge: pro-rata cash basis (50% paid â†’ 50% of VAT becomes due) â€” Cameroon is conservative; we model **on-payment** (full VAT recognised when first payment received). Document this in `docs/taxation_module.md`.

**Touch list**
- One migration adding `vat_scheme_code` to `company_tax_profiles`.
- `vat_cash_basis_recompute_service.py` (new).
- Hook into `customer_payment_service` and `supplier_payment_service` post-allocation paths (as a collaborator, not a UoW owner).
- Tests: `test_slice_t32_cash_basis.py` â€” invoice in March, payment in April â‡’ VAT lands in April return under CASH; lands in March under ACCRUAL.

**Acceptance**
- CompanyTaxProfile dialog gets a "VAT scheme" combo. Switching to CASH and posting an invoice + payment in different periods routes correctly.

---

## PHASE B â€” Statutory completeness (Cameroon DGI)

---

### Slice T33 â€” Reverse-charge VAT (`auto-liquidation` / TVA pour compte)
**Problem fixed:** Â§1.9, Â§3 L29 / L46.

**Scope**
- Add `is_reverse_charge: bool` to `tax_codes`. Default False.
- Migration adds the column; seed adds two new tax codes: `VAT-RC-19.25` (services from abroad, reverse-charged at 19.25%) and `VAT-RC-EXEMPT` placeholder.
- Posting services: when a purchase bill carries a reverse-charge tax code, the JE generator creates **two symmetric postings** in the same JE:
  - Dr expense, Cr supplier (gross â€” same as normal)
  - Dr 4452 (input VAT recoverable on imports) Cr 4434 (output VAT self-assessed) â€” equal & opposite, tax-amount each side
- `tax_fact_service.py` writes **two** `posted_tax_lines` for a reverse-charge bill: one `direction=PURCHASE` (recoverable input), one `direction=SALES` (output self-assessed). Both flow to the return automatically.
- L29 (input recoverable on foreign services) and L46 (VAT retained abroad) populate from these.

**Touch list**
- Constants: 2 new account-code constants `RC_INPUT_VAT_ACCOUNT_CODE="4452"`, `RC_OUTPUT_VAT_SELF_ACCOUNT_CODE="4434"`.
- Migration: `tax_codes.is_reverse_charge` + tax-code seed update.
- `services/purchase_bill_posting_service.py` â€” branch on `is_reverse_charge`.
- `services/tax_fact_service.py` â€” accept dual-fact emission.
- Tests `test_slice_t33_reverse_charge.py`: a 1,000 XAF foreign-services bill produces a JE with 0 net P&L tax impact, two posted_tax_lines, populates L29 and L46.

**Acceptance**
- Importer of consultancy services from France posts a bill, return shows L29 and L46, settlement JE nets to zero VAT impact (collected = recovered).

---

### Slice T34 â€” Pro-rata dÃ©duction (Art. 147 CGI) â€” partial exemption
**Problem fixed:** Â§1.7, Â§3 L24 / L31.

**Scope**
- New table `company_pro_rata_history(company_id, fiscal_year, provisional_pct, final_pct, computed_at, notes)`.
- New service `ProRataService` â€” exposes:
  - `get_provisional_for_year(company_id, year)` â€” returns the prevailing provisional %.
  - `compute_provisional(company_id, year)` â€” formula: `taxable_turnover / (taxable_turnover + exempt_turnover)` from prior year.
  - `record_final(...)` â€” entered manually after year-end, triggers `rÃ©gularisation` adjustment JE.
- Aggregator: when company has `vat_uses_pro_rata=True` and tax_code has `is_recoverable=True` AND `subject_to_pro_rata=True`, multiply input VAT by provisional %.
- L24 / L31 populate from this.
- New permission `taxation.pro_rata.manage`.

**Touch list**
- Migration adds `vat_uses_pro_rata: bool`, `subject_to_pro_rata: bool` (on tax_codes for capital-goods exclusion) + new `company_pro_rata_history` table.
- Service + dialog + sidebar entry under Tax Profile.
- Tests `test_slice_t34_pro_rata.py`.

**Acceptance**
- A bank with 30% taxable / 70% exempt revenue mix sees only 30% of input VAT in L30 / L37; year-end adjustment dialog produces a correction JE.

---

### Slice T35 â€” VAT amendment / `dÃ©claration rectificative`
**Problem fixed:** Â§1.11.

**Scope**
- New return statuses: `RETURN_STATUS_AMENDED` (the original), `RETURN_STATUS_AMENDMENT_DRAFT`, `RETURN_STATUS_AMENDMENT_FILED`.
- New column `tax_returns.parent_return_id: int | None`.
- New service method `TaxReturnService.amend_filed_return(return_id) â†’ new draft return with parent_return_id set`.
- Settlement service generates an **adjustment JE** (delta only) when amendment is filed: difference between new totals and original totals.
- UI: filed return dialog gains "Amend" button (gated by `taxation.returns.amend`).
- Audit chain: the original return's `status_code` flips to `AMENDED`; the new return is the active one.

**Touch list**
- Migration: add `parent_return_id` FK + index, expand return status enum.
- New permission.
- Tests `test_slice_t35_amendments.py`: amend flow produces correct delta JE; double-amend chain works.

**Acceptance**
- Operator can right-click a filed return â†’ Amend â†’ edit drafts â†’ file amendment â†’ settlement journal posts the delta only.

---

### Slice T36 â€” Credit carry-forward chain (L25 â† previous L43)
**Problem fixed:** Â§1.12.

**Scope**
- New column `tax_returns.previous_credit_brought_forward: Decimal` (nullable).
- On draft, the service queries the prior period's return: `prior.l43_credit_carry_forward`. This becomes `current.previous_credit_brought_forward` and surfaces as L25.
- L37 = L30 + L25 (recovered VAT augmented by carried credit).
- Bridges naturally with T35 amendments (amendment of period N also recomputes the carry-forward into N+1).

**Touch list**
- Migration: column + index on `(company_id, period_end DESC)` for fast prior-period lookup.
- `vat_return_form_layout.py` reads L25 directly.
- Tests `test_slice_t36_credit_carryforward.py`.

**Acceptance**
- A persistent net-credit company sees L25 of month N+1 = L43 of month N.

---

### Slice T37 â€” Withholding VAT integration (`prÃ©compte TVA` â€” L45)
**Problem fixed:** Â§1.10, Â§3 L45.

**Scope**
- Existing `withholding_tax_certificate_service.py` extended: when a customer-payment is processed and the customer has `withholds_vat=True`, the system records a `WHTCertificate(kind='VAT_RETAINED')` with the withheld amount.
- New aggregator method: sum of VAT-WHT certificates for the period populates L45.
- Settlement JE: L45 amount becomes a Dr 4459 (VAT receivable from withholdings) entry, reducing net payable.
- Customer master gains `withholds_vat: bool` flag.

**Touch list**
- Migration: `customers.withholds_vat`, `withholding_certificates.kind`.
- Settlement service updated.
- Tests `test_slice_t37_vat_withholding.py`.

**Acceptance**
- Sale to a state body that withholds VAT produces a certificate; the next return reduces VAT payable by L45; settlement JE reflects the receivable.

---

### Slice T38 â€” Capital-goods scheme (`rÃ©gularisation des biens d'investissement`)
**Problem fixed:** Â§1.8.

**Scope**
- New table `vat_capital_goods_register(id, company_id, fixed_asset_id, acquisition_date, base_amount, vat_recovered_initial, monitored_years=5, status_code, notes)`.
- New service `VatCapitalGoodsService` â€” exposes:
  - `register(...)` â€” called when posting a fixed-asset purchase tagged as capital good.
  - `compute_annual_adjustment(year)` â€” for each registered asset, compute the adjustment if pro-rata changed by â‰¥ 10 percentage points.
  - `dispose_asset(...)` â€” reverse remaining VAT recovery proportionally.
- Adjustments flow into L34/L35 of the form.

**Touch list**
- Migration: new table + FK to `fixed_assets`.
- Service + integration with fixed-asset disposal flow.
- Tests `test_slice_t38_capital_goods.py`.

**Acceptance**
- A 50M XAF building purchase with 100% deduction at year 0; pro-rata drops to 60% at year 2 â‡’ year-2 VAT return shows a 4M XAF adjustment in L35.

---

### Slice T39 â€” Excise duty (L18) and lodging tax (L19) tax types
**Problem fixed:** Â§3 L18, L19.

**Scope**
- Add `TAX_TYPE_EXCISE` and `TAX_TYPE_LODGING` constants.
- Excise sub-categories: alcohol / tobacco / telecoms / sugar â€” per-product-category tax codes.
- Aggregator picks them up via `return_box_code='L18'` / `L19'` like all other VAT lines (slice T30 made this generic).

**Touch list**
- Constants + seed.
- Tests confirm L18/L19 populate.

**Acceptance**
- A telecoms operator with excise-tagged sales sees L18 populated.

---

## PHASE C â€” Operational discipline

---

### Slice T40 â€” Drill-down from return â†’ contributing source documents
**Problem fixed:** Â§2.3, Â§4.2.

**Scope**
- Right-click / double-click an L-row in `TaxReturnDetailDialog` â‡’ opens a `VATLineDrillDownDialog` showing every contributing transaction (date, doc number, customer/supplier, base, tax, link to source).
- Backed by a new repository method `PostedTaxLineRepository.list_facts_for_return_line(return_id, line_code)`.
- "Open document" button uses the existing universal-search entity map to navigate.

**Touch list**
- New dialog + handler.
- Repo method.
- No migration.

**Acceptance**
- Double-click L17 â‡’ dialog with all standard-rate sales for the period, totals reconcile to L17.

---

### Slice T41 â€” Exception / exclusion report
**Problem fixed:** Â§2.3 cont.

**Scope**
- New page section `VATExceptionReportPanel` on `TaxCompliancePage`. Shows three buckets for the selected period:
  1. **Excluded transactions** â€” invoices in period that have no tax code, or zero-rate but missing export evidence
  2. **Foreign currency unconverted** â€” flagged for T44
  3. **Draft documents** â€” invoices/bills not yet posted
- Backed by `tax_dashboard_service.list_period_exceptions(company_id, period_start, period_end)`.

**Touch list**
- New service method.
- Panel widget.
- Tests `test_slice_t41_exceptions.py`.

**Acceptance**
- Period with one zero-rate sale lacking export-evidence produces an exception row.

---

### Slice T42 â€” Late-claim auto-rollover
**Problem fixed:** Â§2.4, Â§1.6 partially.

**Scope**
- Aggregator broadens its filter to: `tax_point_date BETWEEN period_start AND period_end` **OR** (`tax_point_date < period_start` AND `posted_at > prior_filed_return.filed_at` AND `not in any other return`).
- New column `posted_tax_lines.included_in_return_id: int | None` to mark inclusion, preventing double-counting.
- Service stamps this column on draft and clears on redraft.

**Touch list**
- Migration: `posted_tax_lines.included_in_return_id` (nullable FK to tax_returns).
- Aggregator rewrite.
- Tests `test_slice_t42_late_claims.py` covering: late invoice for March posted in May â‡’ shows in May return with a `[late claim]` annotation.

**Acceptance**
- May return shows a "Late claims" sub-section under each L-line listing the carried-over March entries.

---

### Slice T43 â€” VAT period lock distinct from fiscal-period lock
**Problem fixed:** Â§5.4.

**Scope**
- New table `vat_period_locks(company_id, period_start, period_end, tax_type_code, locked_at, locked_by_user_id, return_id)`.
- On `file_return`, automatically insert a lock row for the period.
- Posting services consult `vat_period_lock_repository.is_locked(company_id, tax_point_date, tax_type_code)` and **reject** new postings whose tax point falls inside a locked VAT period (ValidationError "VAT period filed; backdating prohibited. Amend the return instead.").
- Override permission `taxation.periods.unlock` for tax admins.

**Touch list**
- Migration: new table.
- New service `VATPeriodLockService` + repository.
- Hook 4 posting services.
- Tests.

**Acceptance**
- Filing March return on 15-April locks March; attempting to post a 30-March invoice on 16-April raises ValidationError.

---

### Slice T44 â€” Multi-currency VAT
**Problem fixed:** Â§2.5.

**Scope**
- Add `tax_amount_reporting_currency`, `taxable_base_reporting_currency`, `exchange_rate`, `rate_source` to `posted_tax_lines`.
- Posting services convert VAT amounts to XAF at the **tax-point-date** rate (BEAC official rate; rate source is configurable).
- Aggregator sums the reporting-currency columns.
- Document headers already carry `currency_code`; we add `vat_exchange_rate` snapshot.

**Touch list**
- Migration: new columns on `posted_tax_lines`.
- Currency rate provider (existing) hooked into posting.
- Tests for USD invoice â‡’ XAF VAT.

**Acceptance**
- A USD-denominated sales invoice produces XAF VAT in the return at the historic rate.

---

### Slice T45 â€” VAT control reconciliation report & dashboard tile
**Problem fixed:** Â§2.9, Â§4.3.

**Scope**
- New report: "VAT Control Reconciliation" â€” for a given period, three columns side by side:
  1. GL balance of 4434 (output) and 4452 (input)
  2. Sum of `posted_tax_lines` per direction
  3. Sum reported on filed returns
- Variance column highlights non-zero differences.
- Tile on `TaxDashboardPage`: shows current variance with red/green status.
- New service `VATReconciliationService`.

**Touch list**
- New service + page widget.
- Tests.

**Acceptance**
- A controller can confirm "GL = facts = returns" with one screen.

---

## PHASE D â€” UX and legal-faithfulness polish

---

### Slice T46 â€” Form regime checkbox + signature block + certification statement
**Problem fixed:** Â§3 regime, Â§4.1, Â§4.4.

**Scope**
- PDF reads `CompanyTaxProfile.tax_regime_code` and ticks **only** the matching checkbox (Actual / Simplified).
- PDF identity panel renders `CompanyTaxProfile.tax_center_code`, `taxpayer_segment_code`, registration#.
- PDF footer adds the legal certification:
  > Je certifie sincÃ¨re et complÃ¨te la prÃ©sente dÃ©claration / I certify the present declaration to be true and complete.
  
  Plus signature block (`Fait Ã  ____, le ____, signature et cachet`), operator-name, capacity field.
- Same on the on-screen viewer (subtle banner).

**Touch list**
- `tax_return_pdf_export_service.py` rendering changes only.
- No migration.

**Acceptance**
- Simplified-regime taxpayer prints a return that ticks "Simplified" not "Actual".

---

### Slice T47 â€” VAT periods state machine (review-lock-file)
**Problem fixed:** Â§2.2, Â§4.6.

**Scope**
- Expand return status enum: `DRAFT â†’ READY_FOR_REVIEW â†’ APPROVED â†’ FILED â†’ SUBMITTED_AWAITING_CONFIRMATION â†’ SUBMITTED_CONFIRMED`.
- Permissions: `prepare`, `review`, `approve`, `file`, `confirm`.
- Post-draft, the return goes to REVIEW; reviewer toggles APPROVED; only APPROVED can be filed.
- "Re-draft" allowed from REVIEW (resets to DRAFT). Forbidden from APPROVED unless reverted.
- Stale-draft warning: if posted_tax_lines exist with `included_in_return_id IS NULL` AND tax_point in the period, draft is "stale" â€” UI shows warning.

**Touch list**
- Status enum migration (string column, no FK; data migration sets existing FILED â†’ FILED).
- 5 new permissions in RBAC catalog.
- Workflow service methods + dialogs.
- Tests for state-machine transitions.

**Acceptance**
- 4-eye filing: preparer drafts, controller approves, manager files. Re-draft from REVIEW works; from APPROVED is forbidden.

---

### Slice T48 â€” Annexes (`Ã©tats annexes`) â€” supplier/customer breakdowns
**Problem fixed:** Â§3 annexes.

**Scope**
- New report types: `vat_customers_annex.xlsx` (per-customer sales summary, NIU-keyed) and `vat_suppliers_annex.xlsx` (per-supplier purchases summary).
- DSF export already builds the foundation â€” we generalise for monthly use.
- Required when annual customer/supplier turnover exceeds DGI threshold (configurable).

**Touch list**
- New service `VATAnnexExportService`.
- Tests.

**Acceptance**
- A monthly return can be filed with attached annex Excel containing supplier-NIU breakdown.

---

## PHASE E â€” Governance and integration

---

### Slice T49 â€” Immutable filed-return guard + view-audit
**Problem fixed:** Â§5.1, Â§5.2, Â§5.3.

**Scope**
- DB-level CHECK constraint or service-level guard preventing `clear()` on lines of a return whose status_code âˆˆ {FILED, AMENDED, ...}. Lines table gains `is_immutable: bool` set on filing.
- New audit event `TAX_RETURN_VIEWED` recorded when `TaxReturnDetailDialog` opens (debounced â€” only once per session per return). Permission gate so this only fires for SOX-tier installations.

**Touch list**
- Migration adds the constraint.
- Audit event type added to catalog.

**Acceptance**
- Manual `lines.clear()` on a filed return raises ConflictError; viewing a filed return appears in audit log.

---

### Slice T50 â€” E-filing scaffold
**Problem fixed:** Â§2.7.

**Scope**
- Generate a structured XML/JSON payload per DGI schema (when published) â€” start with a frozen "Seeker DGI v1" schema we control, ready for a future DGI Mecef integration.
- New service `VATEFilingPayloadService` producing the file.
- Capture submission acknowledgement: `tax_returns.submission_payload_hash`, `submission_acknowledgement_id`, `submission_authority_timestamp`.
- API integration deferred (out of scope per CLAUDE.md Â§2 "no fragile fintech integrations") â€” but the payload and persistence are ready.

**Touch list**
- Migration adds 3 columns.
- New service + dialog "Generate e-filing payload".

**Acceptance**
- Operator can produce a signed XML/JSON file ready for DGI portal upload; payload hash is stored for non-repudiation.

---

## Cross-cutting

### Operational hygiene (applied across every slice)
- Every slice ships with: Alembic up + down round-trip, â‰¥ 5 unit tests, smoke script update, `docs/taxation_module.md` chapter update, repo-memory entry.
- No slice is merged without `python -m pytest -q` green and `scripts/smoke_tax_compliance.py` green.

### Backward compatibility
- Every migration is **additive** (new columns nullable / new tables). No drops.
- Every new behaviour is gated by either:
  - a `CompanyTaxProfile` opt-in flag (`vat_uses_tax_point`, `vat_uses_pro_rata`, `vat_scheme_code`), or
  - an explicit feature constant.
- Existing 600 tests must remain green at every slice boundary.

### Phase ordering rationale
- **Phase A first** because Â§1.1 is a correctness bomb. Every later slice depends on a single, trusted aggregation source.
- **Phase B before C** because period-locking and drill-down (Phase C) are operationally meaningful only once the form actually shows the right numbers (Phase B).
- **Phase D before E** because legal-faithfulness of the printed form (T46) is what stops the system from producing technically-incorrect documents today.
- **Phase E last** because immutability constraints + e-filing depend on a stable, validated lifecycle (Phase D's state machine).

### Suite-wide regression budget
- Each phase adds tests; phases A-E together add â‰ˆ 120-180 new tests.
- Suite target after Phase A: â‰¥ 620 pass.
- Suite target after Phase E: â‰¥ 720 pass.

---

## Effort and risk profile (relative)

| Slice | Risk | Cross-module impact |
|---|---|---|
| T29 unified aggregator | High | sales / purchases credit-note posting |
| T30 box-code aggregation | Medium | tax-code seed |
| T31 tax-point | Medium | 4 posting services |
| T32 cash basis | Medium | 2 payment services |
| T33 reverse charge | High | purchase posting + JE generator |
| T34 pro-rata | High | new schema + adjustment JE |
| T35 amendments | Medium | settlement service delta logic |
| T36 carry-forward | Low | aggregator only |
| T37 WHT integration | Medium | settlement + customer master |
| T38 capital goods | Medium | fixed-assets module touch |
| T39 excise/lodging | Low | additive |
| T40 drill-down | Low | UI |
| T41 exception report | Low | new service |
| T42 late claims | Medium | aggregator |
| T43 VAT lock | Medium | 4 posting services |
| T44 multi-currency | Medium | posting services |
| T45 reconciliation | Low | new service |
| T46 form polish | Low | rendering |
| T47 state machine | High | RBAC + lifecycle |
| T48 annexes | Low | export service |
| T49 immutability + view-audit | Low | constraint + audit |
| T50 e-filing scaffold | Low | additive |

High-risk slices (T29, T33, T34, T47) get extra-thorough review and double the test budget.

---

## Deferred / out of scope (intentionally)

- DGI Mecef portal API integration (per CLAUDE.md Â§2 "no fragile fintech integrations") â€” payload generation only.
- Real-time exchange-rate API (BEAC) â€” daily-snapshot table is enough.
- Integration with bank-statement-matching for VAT remittance (requires a separate bank-recon slice already in the broader roadmap).
- VAT MOSS / OSS (EU-specific schemes) â€” not relevant for Cameroon.
- Triangulation / chain-transaction VAT logic (EU intra-community) â€” not relevant for Cameroon.

---

## Recommended sequencing for delivery

1. Ship **T29** alone first (single-slice release). It's the correctness fix.
2. Then **T30 + T31 + T32** as Phase A pack.
3. Phase B in two waves: T33-T35 (reverse charge, pro-rata, amendments), then T36-T39 (carry-forward, WHT, capital goods, excise).
4. Phase C in one wave (T40-T45) â€” operational features.
5. Phase D + E as final polish (T46-T50).

This sequencing means **after T29 only**, the system is already substantially more trustworthy than today. Each subsequent slice adds capability without re-opening prior correctness questions.
