

# Seeker Accounting — Taxation Module: Research & Implementation Plan (Cameroon)

## 1. Scope and grounding

This plan is grounded in 31 DGI official publications already extracted to tax_research (CGI 2024 anglais, Finance Law 2025 projet, fact sheets for VAT/IS/IRPP/IRCM/BNC/IGS/DA, DSF 2025 Guide, Online DSF Reporting Process, Annual Income Declaration Notice, SME regime sheet, Excise Duties sheet, OTP guide for third-party payments, etc.). Any cited rate, deadline, or article is traceable back to those files.

Per CLAUDE.md, this is **research + design only** — no code changed. The purpose is to produce a stable, slice-phased plan that the team can execute without re-opening direction.

---

## 2. Cameroon tax landscape — what the software must actually handle

### 2.1 Taxes that touch everyday accounting entries
| Tax | Rate / scale | Period | Due date | OHADA/CAC notes |
|---|---|---|---|---|
| **VAT (TVA)** | 19.25% (17.5% base + 10% CAC) general; 0% exports / specific exempts | Monthly | 15th of following month | Invoiced VAT → 4431-4435; recoverable → 4451-4456; credit carried fwd → 4449; settlement → 4441 |
| **Excise duties (Droits d'accises)** | 2%, 5%, 12.5%, 25%, 30%, 50% ad valorem + specific rates (FCFA/cl, FCFA/unit) | Monthly (same return as VAT) | 15th of following month | Applies before VAT on certain products (alcohol, tobacco, sugary drinks, cosmetics, vehicles, telecoms, digital content, packaging) |
| **Corporate Income Tax (IS)** | 30% standard, 25% if turnover ≤ 3B FCFA; + 10% CAC | Monthly advances (2% of turnover) + annual balance | Advances: 15th of following month. Balance: 15 Mar (DGE) / 15 Apr (CIME, CSI) / 15 May (CDI) | 444x "État – impôts sur bénéfices" accounts |
| **IRPP – Salaries** | Progressive 10/15/25/35% after 30% abatement + 500,000 allowance + CNPS; + 10% CAC; not withheld if monthly salary < 62,000 | Monthly withholding | 15th of following month | Tied to payroll; already partly handled in payroll module |
| **IRPP – IRCM (capital income)** | 16.5% normal (15% + CAC); 11% listed BVMAC; 5.5% bonds ≥5y; 33%/38.5% punitive | At source by payer | 15 days after payment (dividends: within 9 months of year-end at latest) | Booked against dividends/interest paid |
| **IRPP – BNC (professional)** | 30% + CAC; minima 2% réel / 5% simplifié of turnover | Monthly advance + annual | Same as IS deadlines | Applies to self-employed professionals using the app |
| **IRPP – Land income (RF)** | 10% (rent to individuals, libératoire) / 25%-30% (rent to professionals) | Monthly withholding by tenant where applicable | 15th of following month | "Précompte sur loyer" |
| **IGS** | Tariff schedule on turnover; 50% abatement if CGA member | Annual | Per local tax code | Replaces old Impôt Libératoire + Régime Simplifié for small taxpayers |
| **TSR (special tax on non-resident income)** | 3%, 5%, 7.5%, 10%, 15% | Monthly withholding | 15th of following month | Applies to services paid to non-residents |
| **Patente / Licence** | Scale per CGI | Annual | Per local fiscal code | Company-level, not transaction-level |
| **CAC (Centimes Additionnels Communaux)** | +10% on most direct and indirect taxes | Follows underlying tax | Follows underlying | **Automatic uplift**; must be calculable on the fly and traceable on every tax line |
| **Penalties** | 1.5% interest/month (cap 50%) + 10%/month late penalty (cap 30%); fraud surcharges 30%/100%/150% | | | Recorded at declaration, not line-level |

### 2.2 Regime dimension (drives everything)
- **Impôt Libératoire** (IGS zone): turnover ≤ 10M FCFA — no VAT, no monthly IS, flat tariff
- **Simplifié**: 10M < turnover ≤ 50M — monthly IS advance + withholdings, no full VAT on output (generally)
- **Réel**: turnover > 50M — full VAT, monthly IS advance at 2%, full withholdings, full DSF
- **CGA membership**: 50% abatement on taxable profit (non-professionals)
- **Tax centers**: CDI / CIME / CSI PLI / CSI EPA / DGE — drive deadlines and filing channel

**This is a first-class company attribute**, not a preference — it changes which taxes apply, which returns exist, and all deadlines.

### 2.3 DSF (Déclaration Statistique et Fiscale) — annual return
- Electronic filing via **GOVIN** at www.impots.cm
- Three channels: **DGI Excel template upload** (preferred non-web-based), **manual interface entry**, **REST API** (web-based accounting systems — **this is the real target for Seeker**)
- Taxpayer needs NIU (Unique Identifier Number) — must live on the Company
- Has 8 API endpoints: connect, add/delete declaration, list declarations (all / by year), get specific, add/modify/delete page, submit
- Balance payable in XAF by default; FX rate required if paying in EUR/USD
- Generates tax notice (avis d'imposition) and acknowledgement of receipt (ARE) that must be archived

### 2.4 Other mechanics the engine must know about
- **Pro-rata VAT deduction** for mixed activities (taxable + exempt)
- **Fixed-asset VAT recovery adjustment** (regularisation) over retention period
- **VAT credit carry-forward** via 4449 (vs immediate refund for exporters / specific regimes via refund request workflow)
- **Withholding at source** in two directions: collected (company withholds from supplier) and suffered (customer withholds from company → tax credit)
- **Territoriality**: IS only on Cameroon-sourced profit; DTA (double-tax treaties with US, Canada, France, and others) override
- **"Minimum de perception"** rule: if computed IS/IRPP is below 2% (réel) or 5% (simplifié) of turnover, the minimum applies
- **Rounding and presentation**: all FCFA integer; CAC computed and displayed on its own line
- **Exemption categorisation**: specific exempt, 0% export, true out-of-scope, intra-CEMAC, etc. — different reporting boxes

---

## 3. Gap analysis vs current Seeker codebase

### 3.1 What exists and is usable as-is
- `TaxCode` master entity (code, name, tax_type_code, calculation_method_code, rate_percent, is_recoverable, effective_from/to, company-scoped, temporal key) — **solid foundation for rates**
- `TaxCodeAccountMapping` (sales/purchase/tax_liability/tax_asset accounts) — **correct shape** for mapping to 4431-4435 and 4451-4456
- Line-level tax capture on sales invoices, purchase bills, quotes, inventory docs — **good**
- Posting services (sales/purchase) correctly credit/debit mapped VAT accounts — **good**
- `TaxSetupService` with CRUD + permissions `reference.tax_codes.*` / `reference.tax_mappings.*` — **good**
- OHADA chart already contains 4431-4435, 4441, 4449, 4451-4456, 4472 — **no schema gap for VAT posting**

### 3.2 Known defects to fix before extending
1. **purchase_bill_service.py** — computes tax as `rate_percent / 100` unconditionally, **ignoring `calculation_method_code`**. Inconsistent with sales (which handles PERCENTAGE/FIXED_AMOUNT/EXEMPT correctly). Must be fixed before we rely on tax codes for excise (FIXED_AMOUNT) or exempt classification.
2. No separation between **statutory taxes** (VAT, excise, WHT) and **ad-hoc line adjustments** — all ride on the same TaxCode today.
3. CAC is **not modeled** — there is no way today to express "19.25% is 17.5% + 10% CAC" or to produce reports showing CAC separately, which is a DGI requirement.

### 3.3 Structural gaps (missing entirely)
| Gap | Impact |
|---|---|
| **Tax regime** per company (Libératoire / Simplifié / Réel) | Cannot drive deadlines, applicable taxes, minimum de perception, or DSF variant |
| **Company tax registration** (NIU, tax center, CAC applicability, CGA membership, DGE/CIME/CSI/CDI) | Required for DSF filing, advance payment calculation, return deadlines |
| **Tax period** (monthly/quarterly/annual, per tax type, per company) | No concept of "VAT period 2025-03" on which to close and file |
| **Immutable posted-tax snapshot** (`PostedTaxLine` / `TaxFact`) | Today we re-read tax amounts from invoice lines — if a posted doc is ever "edited" or re-valued, the VAT return will drift. Accounting truth requires a snapshot at posting time. |
| **Tax return** entity + workflow (draft → review → filed → settled) | No way to actually produce a VAT return, let alone IS advance or IRPP WHT return |
| **Tax return line / box mapping** | Cannot tie accounting figures to the DGI form structure |
| **Tax adjustment** (credits, carry-forwards, manual corrections) | No way to record VAT credit on 4449 or periodic adjustments |
| **Tax payment / settlement** with JE posting | Today paying tax is an ad-hoc bank payment — not linked to a specific return |
| **Withholding at source** in both directions with certificate generation | Cannot handle precompte sur loyer, TSR, WHT suffered/collected |
| **Fixed-asset VAT regularisation** tracking | Needed for asset disposals, pro-rata changes |
| **DSF export/submission** (Excel template + GOVIN API) | Today there is nothing |
| **Pro-rata VAT coefficient** per company/period | Cannot deduct partial VAT when activity is mixed |
| **Territoriality and DTA** metadata | Needed for IS and TSR decisions |
| **Tax reports** (VAT return worksheet, IS advance summary, IRPP monthly, annual reconciliation) | No domain-aware reports today |

---

## 4. Proposed domain model

New feature module: `src/seeker_accounting/modules/tax/` with the standard layers `models/ repositories/ services/ dto/ ui/`. Reference data (`TaxCode`, `TaxCodeAccountMapping`) stays where it is — it is **rate master data**. The new `tax` module is the **tax engine and workflow**.

### 4.1 Entities

**Configuration / setup**
- `TaxRegime` — enum-backed lookup: `LIBERATOIRE`, `SIMPLIFIE`, `REEL`. Drives minimum rates, applicable tax set, return set, deadlines.
- `TaxCenter` — lookup: `DGE`, `CIME`, `CSI_PLI`, `CSI_EPA`, `CDI` (+ region). Drives deadline calendar.
- `CompanyTaxRegistration` — one per company. Fields: `niu`, `tax_regime_id`, `tax_center_id`, `cga_member`, `cac_applicable` (defaults true), `excise_eligible`, `export_oriented`, `effective_from`. Company-scoped, temporal.
- `TaxCalendarRule` — seeded reference data: for each `(tax_type, regime, center)`, describe due-date offset and return type. Keeps deadline logic declarative.

**Rate / treatment refinement (extend existing `TaxCode`)**
- Add fields (new migration) to `TaxCode`: `has_cac` (bool), `cac_rate_percent` (default 10), `base_rate_percent` (the pre-CAC rate), `exemption_kind` (NORMAL / ZERO_EXPORT / EXEMPT_SPECIFIC / OUT_OF_SCOPE / REVERSE_CHARGE), `return_box_code` (which DGI form box this feeds).
- Keep `rate_percent` as the all-in effective rate for posting simplicity (= `base_rate * (1 + cac_rate/100)` where applicable).

**Immutable posted-tax facts (the critical new entity)**
- `PostedTaxLine` — written at the moment a source document is posted. One row per (posted document, line, tax code). Fields include: `company_id`, `fiscal_period_id`, `tax_period_id` (nullable until computed), `source_document_type`, `source_document_id`, `source_line_id`, `direction` (SALES / PURCHASE / WITHHOLDING_COLLECTED / WITHHOLDING_SUFFERED), `tax_code_id`, `taxable_base`, `base_tax_amount`, `cac_amount`, `total_tax_amount`, `is_recoverable`, `posted_at`, `journal_entry_line_id`, `counterparty_id`, `counterparty_nature` (INDIVIDUAL / COMPANY / NON_RESIDENT / GOVERNMENT), `product_kind` (GOODS / SERVICES / FIXED_ASSET / ENERGY / TRANSPORT). **Immutable**. Reversed only by a reversing fact (when a posted document is cancelled/credit-noted).
- This is the authoritative source for every tax return. Reports read this, not invoice lines.

**Periods and returns**
- `TaxPeriod` — `(company_id, tax_type, period_type, period_start, period_end, status)` with status = OPEN / LOCKED / FILED. Independent of accounting fiscal periods (a VAT month may overlap accounting closing).
- `TaxReturn` — one per `(company_id, tax_type, tax_period_id)`. Status: `DRAFT → UNDER_REVIEW → READY_TO_FILE → FILED → SETTLED → CLOSED`. Fields: identifier, submitted_at, filed_by_user, external_reference (GOVIN receipt number), declared_total_due, declared_total_payable, credit_carried_forward, penalties_self_assessed, payment_deadline.
- `TaxReturnLine` — one per box on the DGI form. Fields: `box_code`, `box_label`, `declared_base`, `declared_tax`, `system_computed_base`, `system_computed_tax`, `override_reason`. The difference between system-computed and declared values is explicit and auditable.
- `TaxReturnAttachment` — appendices (see DSF guide § 12: list of corresponding attachments per form).

**Settlement and payments**
- `TaxPayment` — records actual payment (cash/bank) against a `TaxReturn`. Posts a JE. Links to payment channel (Mobile Tax, bank transfer, OTP platform).
- `TaxCreditCarryforward` — credit VAT moved to 4449 at one period and consumed at a later period.
- `TaxRefundRequest` — for VAT refund claims (exporters, specific regimes). Own workflow.

**Withholding**
- `WithholdingCertificate` — issued when the company withholds from a supplier (TSR, precompte loyer, IRCM). Fields: beneficiary, base, rate, amount, certificate number, issue date.
- `WithholdingSuffered` — when a customer withholds from the company; becomes a tax credit asset against IS.

### 4.2 Services (the business layer)

Strict UI → Service → Repository flow per CLAUDE.md. No posting in UI, no tax logic in repos.

- **`TaxDeterminationService`** — given `(company, date, party, item/account, nature)` resolves the correct `TaxCode(s)` to apply. Handles regime rules, territoriality, exemptions, default tax for an account. This is what invoice/bill UIs will call to auto-populate tax code instead of forcing user choice.
- **`TaxCalculationService`** — pure calculation: base × rate, adds CAC, splits base_tax_amount / cac_amount, applies rounding (FCFA integer), honors `calculation_method_code` (PERCENTAGE / FIXED_AMOUNT / PER_UNIT for excise / EXEMPT). Replaces the inconsistent inline calculation in sales vs purchases services.
- **`TaxFactService`** — called by posting services (`SalesInvoicePostingService`, `PurchaseBillPostingService`, `PayrollPostingService`, etc.) to write `PostedTaxLine` rows as part of the same transaction as the journal entry. Also writes reversing facts when a document is cancelled.
- **`TaxPeriodService`** — opens, locks, closes tax periods per company per tax type. Independent of accounting period closing service but coordinated with it.
- **`TaxReturnService`** — draft generation (aggregates `PostedTaxLine` into form boxes), review, lock, file. Produces the return workbook / API payload.
- **`TaxSettlementService`** — posts the JE for tax settlement. For VAT: debit 4431-4435, credit 4451-4456, balance on 4441 (owed) or 4449 (credit carried fwd). For IS advance: debit 4422, credit cash. For IRPP salary: debit payroll liability, credit cash. Links the JE to the `TaxReturn`.
- **`DSFExportService`** — produces the DGI Excel template with `FICHE_R2` correctly coded (per DSF Guide § 10), and drives the GOVIN REST API (8 endpoints). Excel first, API second.
- **`WithholdingCertificateService`** — numbering, issuance, PDF rendering, and reporting.
- **`TaxRefundService`** — refund claim workflow.

Business exceptions to add: `TaxPeriodLockedError`, `TaxReturnAlreadyFiledError`, `TaxRegistrationMissingError`, `TaxCodeNotApplicableError`, `MissingNIUError`.

### 4.3 UI surfaces

- **Existing Reference Data → Tax Codes**: extend the current screen (no redesign — CLAUDE.md §21). Add CAC fields, exemption kind, return box code. Keep dialog-first editing.
- **Administration → Tax Registration**: new page, one tab per company showing regime, NIU, tax center, CGA membership, applicable taxes preview, deadline preview.
- **Taxation module** in sidebar (new top-level icon):
  - **Tax Periods** — list per tax type, with status chip (Open / Locked / Filed).
  - **VAT Returns** — workspace-style page because a VAT return is a document workflow, not a simple dialog. Shows system-computed boxes on the left, editable declared values on the right, variances flagged.
  - **IS Advance Payments** — monthly list, auto-computed 2% on turnover, link to JE.
  - **IRPP Payroll Summary** — monthly, reads from payroll module.
  - **Withholding Certificates** — issued + suffered.
  - **Tax Payments** — list + new payment dialog.
  - **Refund Requests** — workflow.
  - **DSF** — annual package assembly screen, shows all appendices status, upload to GOVIN or export Excel.
- **Reports**:
  - VAT Declaration Worksheet (matches DGI form)
  - IS Annual Reconciliation
  - IRPP Monthly Summary
  - Withholding Register (both directions)
  - Tax Payment Register
  - Credit Carry-forward Statement

All tables right-align numerics, clear status chips, dialog-first create/edit (except VAT return and DSF which are document workspaces).

---

## 5. Slice-phased implementation roadmap

Strictly one slice at a time. Each slice is independently shippable and preserves existing behavior.

### Slice T1 — Foundation hardening
**Goal**: make current line-level tax robust enough to build on.
- Fix purchase_bill_service.py to honor `calculation_method_code` (match sales behavior).
- Extract a shared `TaxCalculationService` used by both sales and purchases. No behavior change on the sales side.
- Unit tests covering PERCENTAGE, FIXED_AMOUNT, EXEMPT, and rounding.
- Smoke test: post a bill with a FIXED_AMOUNT tax code, verify JE and amounts.

### Slice T2 — CAC modeling
- Add `base_rate_percent`, `has_cac`, `cac_rate_percent` to `TaxCode` (Alembic additive migration, SQLite + Postgres portable).
- `TaxCalculationService` splits `base_tax_amount` vs `cac_amount` on each line.
- Reference Data UI extended.
- No new workflows yet — posting continues to use the combined rate for the JE, but the breakdown is captured.

### Slice T3 — Company Tax Registration
- New entity `CompanyTaxRegistration` + migration.
- Seed `TaxRegime`, `TaxCenter`, `TaxCalendarRule`.
- Administration page.
- Service validates NIU format, regime consistency with the seeded tax calendar.

### Slice T4 — PostedTaxLine snapshots
- New entity + migration.
- `TaxFactService` wired into `SalesInvoicePostingService`, `PurchaseBillPostingService`. Write `PostedTaxLine` inside the same DB transaction as the JE.
- Reversing facts on cancellation.
- No UI yet — purely a data fact table.
- Validation: posted amounts in `PostedTaxLine` reconcile to JE lines on 4431-4435 / 4451-4456 for a sample period.

### Slice T5 — Tax Period + VAT Return (draft)
- `TaxPeriod` entity + opening/locking service.
- `TaxReturn` + `TaxReturnLine` entities.
- Draft VAT return: aggregates `PostedTaxLine` into DGI VAT boxes, read-only preview.
- UI: Tax Periods list + VAT Return workspace (view only).

### Slice T6 — VAT Return review + file + settlement posting
- Review step allows manual box overrides with reason.
- Lock step marks return `READY_TO_FILE`.
- File step records external reference (GOVIN receipt).
- `TaxSettlementService` posts the JE: Dr 4431-4435, Cr 4451-4456, balancing entry on 4441 (payable) or 4449 (credit c/f).
- Period becomes FILED; `PostedTaxLine` rows in it are frozen.
- Export VAT return to PDF.

### Slice T7 — Tax payments
- `TaxPayment` entity.
- Payment dialog against a `TaxReturn`.
- Posts bank-side JE linked to the return.
- Late-payment interest/penalty calculator (1.5%/month cap 50%, 10%/month cap 30%).

### Slice T8 — Withholding at source (outbound — TSR, precompte loyer, IRCM)
- `WithholdingCertificate` + numbering + PDF.
- Purchase bill / supplier payment hooks to propose withholding.
- Monthly withholding return (same pattern as VAT return, different boxes).

### Slice T9 — Withholding suffered + IS advance
- `WithholdingSuffered` entity; customer-side hooks capture suffered WHT as IS credit.
- Monthly IS advance worksheet (2% × taxable turnover) with JE posting to 4422.
- Annual IS reconciliation worksheet.

### Slice T10 — Payroll/IRPP tie-in
- Payroll module emits `PostedTaxLine` rows for IRPP salary withholding + employer contributions.
- Monthly IRPP return aggregated in the Taxation module.

### Slice T11 — DSF package
- Map `PostedTaxLine` + GL + payroll to the DGI DSF Excel template (all required fiches).
- DSF workspace shows package completeness.
- Excel export first; GOVIN REST API as a later sub-slice.

### Slice T12 — Excise duties
- Extend `TaxCode` with excise-specific calculation methods (per-volume, per-unit).
- Item-level "excise class" attribute.
- Excise return attached to monthly VAT return per DGI.

### Slice T13 — Pro-rata VAT & fixed-asset regularisation
- `ProRataCoefficient` per company per year.
- Apply on purchase VAT recovery.
- Fixed-asset VAT regularisation on disposal or coefficient change (5-year retention for movables, 20-year for real estate per OHADA).

### Slice T14 — VAT refund request
- Refund claim workflow (state machine + attachments).
- Integrates with GOVIN once API slice is done.

### Slice T15 — IGS / Libératoire special path
- Small-taxpayer variant: no VAT, flat tariff, annual declaration. Reuses return workflow with a different ruleset.

---

## 6. Key design decisions and rationale

1. **Keep `TaxCode` as rate master; introduce `PostedTaxLine` as accounting truth.** Rates change over time; facts must not. Reports must never re-derive tax from current rates.
2. **CAC is not a separate tax code; it is a modifier on a tax code.** Storing a combined "19.25%" hides the structure DGI requires on returns. Split into `base_rate` + `cac_rate` from the start.
3. **Tax period ≠ accounting period.** VAT is monthly regardless of accounting calendar. Conflating them breaks closing workflows.
4. **Regime drives rules declaratively.** A seeded `TaxCalendarRule` table is far better than `if regime == SIMPLIFIE` scattered in services.
5. **DSF Excel first, API second.** Lower risk, faster to deliver, and the Excel template is the DGI's own canonical format — matching it forces correctness.
6. **No tax logic in UI, no UI logic in services.** The current split (sales posting service owns VAT posting) is already correct; extend the pattern, don't break it.
7. **Payroll and taxation share facts through `PostedTaxLine`.** Payroll service writes IRPP and CNPS-related rows; Taxation service aggregates them. No cross-module business logic leakage.
8. **All tax values in FCFA integer at storage time**, even though intermediate calculations use `Decimal`. DGI forms and Cameroonian accounting practice round at line level.

---

## 7. Risks and deferred items

**Risks to flag before starting T1:**
- Finance Law 2025 introduces changes that need to be re-read against the seeded calendar before T3 (Projet-de-loi-de-Finances-2025-PRC is captured at 219KB — not fully reviewed in this analysis).
- GOVIN API specification is distributed inside the portal only after API activation (per DSF Guide § 7) — team must enable this on a test NIU to obtain endpoint specs before T11.
- Double-taxation treaty handling (US/Canada/France per tax-laws-Cameroon.txt, CEMAC internally) is complex; explicitly deferred to a post-T15 slice.

**Explicitly out of scope of this plan:**
- Payment gateway integration with Mobile Tax / bank APIs (per CLAUDE.md §2)
- Cross-CEMAC unified tax (UDEAC) consolidation
- E-invoicing compliance (if/when DGI mandates it)
- Transfer pricing documentation

---

## 8. What this plan does **not** change

- No changes to current accounting posting engine, chart of accounts, or existing module boundaries.
- No changes to payroll, sales, purchases, or inventory modules beyond (a) fixing the purchase tax calculation defect in T1, and (b) having their posting services additionally call `TaxFactService` in T4.
- No changes to the shell, sidebar, or theme until T5 introduces the Taxation module entry.
- Existing `TaxCode` + `TaxCodeAccountMapping` keep their current meaning and UI; they gain fields additively.

---

**Summary**: Current codebase has correct reference-data foundation (tax codes, mappings, chart) and correct posting behavior for basic VAT. What's missing is the entire statutory layer — regime, registration, periods, returns, immutable facts, settlements, filing. Plan above delivers this in 15 disciplined slices, Cameroon-law-grounded, starting with a small defect fix (T1) and ending with full DSF + refund + IGS coverage. No code was written. 



Made changes.