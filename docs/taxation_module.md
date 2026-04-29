# Taxation Module — User & Operator Guide

The Taxation module in Seeker Accounting covers Cameroon DGI / OHADA
compliance: company tax profile, compliance calendar, returns, payments,
settlement, withholding tax certificates, DSF Excel export, dashboard,
audit trail, and printable PDF exports.

This document is the operator's reference for slices **T1 through T26**
and reflects the production-shipped behavior of the module.

---

## 1. Scope and architecture

### 1.1 What the module does

- Stores the company's tax-compliance profile (NIU, regime, VAT
  liability, DSF form, tax-mapping readiness flags).
- Tracks the tax compliance calendar — periodic tax obligations for
  VAT, CIT installments, withholding, Patente (business license),
  TSR (specific service tax), and customs duty.
- Drafts, files, and settles tax returns, with strict
  draft → reviewed → filed → settled state transitions.
- Records tax payments and posts the bank-side journal entry against
  settled VAT returns.
- Maintains a withholding-tax certificate register (inbound and
  outbound) so the company can reconcile WHT due-from / due-to the tax
  authority.
- Generates the annual DSF (Déclaration Statistique et Fiscale) Excel
  workbook with form-family-specific fiches plus standalone P&L and
  Balance Sheet sheets.
- Surfaces a compliance dashboard, a chronological taxation audit
  trail, and a printable PDF rendering of any tax return.

### 1.2 Layered architecture

```
UI (TaxCompliancePage, dashboard widgets, dialogs)
    │
    ▼
Services (TaxObligationService, TaxReturnService, TaxPaymentService,
          TaxSettlementService, WithholdingTaxCertificateService,
          DSFExportService, TaxDashboardService, TaxAuditTrailService,
          TaxReturnPDFExportService, CompanyTaxProfileService)
    │
    ▼
Repositories (TaxObligationRepository, TaxReturnRepository,
              TaxPaymentRepository, WithholdingTaxCertificateRepository,
              CompanyTaxProfileRepository, PostedTaxLineRepository)
    │
    ▼
SQLAlchemy models on the shared accounting database
```

UI never opens its own DB session and never imports a repository
directly. All write-side workflows go through service methods that
gate on permissions, validate state transitions, and record audit
events.

### 1.3 Permission catalog (taxation.\*)

| Code                              | Purpose                                                      |
|-----------------------------------|--------------------------------------------------------------|
| `taxation.profile.view`           | View the company's tax-compliance profile                    |
| `taxation.profile.manage`         | Create or update the tax-compliance profile                  |
| `taxation.obligations.view`       | View the compliance calendar                                 |
| `taxation.obligations.manage`     | Create / generate / cancel obligations                       |
| `taxation.returns.view`           | View tax returns and box-level breakdown                     |
| `taxation.returns.manage`         | Draft and update tax returns                                 |
| `taxation.returns.file`           | File a return (locks it as submitted)                        |
| `taxation.returns.settle`         | Post the settlement JE for a filed VAT return                |
| `taxation.returns.export_pdf`     | Render a tax return as a printable PDF                       |
| `taxation.payments.view`          | View tax payments                                            |
| `taxation.payments.manage`        | Record tax payments against returns                          |
| `taxation.dsf.export`             | Generate the annual DSF Excel export                         |
| `taxation.withholding.view`       | View the WHT certificate register                            |
| `taxation.withholding.manage`     | Record / update / void WHT certificates                      |
| `taxation.dashboard.view`         | View the consolidated tax dashboard                          |
| `taxation.audit.view`             | View the chronological taxation audit trail                  |

---

## 2. Data model

### 2.1 Core tables

| Table                          | Purpose                                              |
|--------------------------------|------------------------------------------------------|
| `company_tax_profiles`         | Per-company tax profile (NIU, regime, DSF form, etc.)|
| `tax_obligations`              | Compliance calendar entries                          |
| `tax_returns`                  | Filed returns (header)                               |
| `tax_return_lines`             | Box-level breakdown of a return                      |
| `tax_payments`                 | Money paid against a return                          |
| `withholding_tax_certificates` | WHT register (inbound + outbound)                    |
| `posted_tax_lines`             | Posting-side fact table (driven by tax codes)        |

All business tables are scoped by `company_id`. Composite uniqueness on
`(company_id, tax_type_code, period_start, period_end)` for obligations
prevents duplicate periods.

### 2.2 Tax type codes

Defined in [`modules/taxation/constants/__init__.py`](../src/seeker_accounting/modules/taxation/constants/__init__.py):

`VAT`, `CIT_INSTALLMENT`, `WITHHOLDING`, `PATENTE`, `TSR`, `CUSTOMS`.

### 2.3 Status transitions

**Obligations** — `OPEN → IN_PROGRESS → FILED → PAID`, with
`OVERDUE` derived from `due_date < today` when still open, and
`CANCELLED` as a terminal state.

**Returns** — `DRAFT → REVIEWED → FILED → AMENDED?`. `CANCELLED`
is terminal. A FILED VAT return with `journal_entry_id IS NULL` is
"unsettled" and the eligibility target for settlement.

---

## 3. Workflows

### 3.1 Set up the company tax profile (T2)

1. Open *Taxation → Profile*.
2. Enter NIU, regime, fiscal-year boundaries, VAT liability, DSF form,
   and confirm the chart-of-accounts tax mapping is complete.
3. Save. Service: `CompanyTaxProfileService.upsert_profile`.

### 3.2 Generate the compliance calendar

| Tax type        | Method                                          | Cadence         | Default due day |
|-----------------|-------------------------------------------------|-----------------|-----------------|
| VAT             | `generate_monthly_vat_obligations`              | Monthly (12)    | 15th of next month |
| CIT installment | `generate_quarterly_cit_installments`           | Quarterly (4)   | 15th of next month |
| Withholding     | `generate_monthly_withholding_obligations`      | Monthly (12)    | 15th of next month |
| Patente         | `generate_annual_patente_obligation`            | Annual (1)      | Feb 28           |
| TSR             | `generate_monthly_tsr_obligations`              | Monthly (12)    | 15th of next month |
| Customs         | `create_customs_duty_obligation`                | Per declaration | Caller-supplied  |

All generators are idempotent — re-running them for the same year /
declaration date returns the existing obligations without duplicating.

### 3.3 Draft, review, and file a VAT return

1. *Taxation → Compliance* — pick an `OPEN` VAT obligation.
2. **Draft return** (`TaxReturnService.draft_vat_return`) — pulls
   posted output / input VAT facts from `posted_tax_lines` for the
   period and writes the draft return + lines.
3. **Review and edit** — adjust line amounts as needed (still
   `DRAFT`).
4. **File** (`TaxReturnService.file_return`) — captures filing
   timestamp, OTP / external reference, locks the return.

### 3.4 Settle a filed VAT return (T15 / T17)

For a `FILED` VAT return with no journal entry yet:

1. From *Tax Compliance* select the return → click **Settle return**.
2. The `Settle VAT Return` dialog previews the projected JE
   (`TaxSettlementService.preview_settlement`):
   - Dr Output VAT (account 4432) × period total
   - Cr Input VAT recoverable (account 4452) × period total
   - Cr VAT payable (4441) **or** Dr VAT credit carry-forward (4449)
3. Confirm the settlement date and click **Post Settlement**
   (`TaxSettlementService.settle_return`). The JE is posted, the
   return's `journal_entry_id` is set, and `settled_at` is stamped.

Eligibility gating checks on the page:

- `tax_type_code == VAT`
- `status_code == FILED`
- `journal_entry_id IS NULL`
- caller has `taxation.returns.settle`

### 3.5 Record a tax payment (T16)

1. From a settled VAT return, click **Record Payment**.
2. Pick the treasury account; enter date, amount, method, reference.
3. `TaxPaymentService.record_payment` writes the `tax_payments` row
   and posts a balanced bank-side JE:
   `Dr 4441 (VAT payable) / Cr <treasury account>`.

For non-VAT returns or record-only flows the treasury account is
optional and the JE is skipped.

### 3.6 Withholding-tax certificate register (T13)

`WithholdingTaxCertificateService` records inbound (received from a
public-sector / large-taxpayer customer) and outbound (issued to a
supplier) certificates. Each certificate stores direction,
counterparty, NIU, tax code, taxable base, and tax amount. Voiding is
a soft state change. Active inbound balances are surfaced in the DSF
export and on the dashboard.

### 3.7 Annual DSF export (T5 / T9 / T25)

1. *Taxation → DSF Export* (or `DSFExportService.generate`).
2. Pick the fiscal year and output path (`.xlsx`).
3. The workbook contains:
   - **Company Profile** — header card.
   - **VAT Summary**, **VAT Detail**, **Payments** — period activity.
   - **Withholding Certificates** — full register for the year (T13).
   - **Income Statement (P&L)** — standalone OHADA P&L (T25).
   - **Balance Sheet** — standalone OHADA BS, asset and liability
     pages separated by a divider row (T25).
   - **Readiness** — list of `info / warning / error` issues.
   - **Form-family fiches** — R1 / R2 / R3 / R4 / annexes per the
     selected DSF form.
4. The export never blocks on a downstream report failure; missing
   amounts surface as readiness warnings (`FICHE_R3_AMOUNTS_UNAVAILABLE`,
   `FICHE_R4_AMOUNTS_UNAVAILABLE`) and the corresponding cells are left
   blank.

### 3.8 Dashboard (T22)

`TaxDashboardService.get_dashboard(company_id, fiscal_year, *,
as_of_date=None)` returns a `TaxDashboardSnapshotDTO` aggregating:

- total / open / overdue / paid / cancelled obligation counts
- per-tax-type counts (`by_tax_type`)
- `returns_draft`, `returns_filed`, `returns_settled`,
  `returns_filed_unsettled_vat`
- `total_payments_ytd`, `total_due_filed_returns_ytd`
- `wht_inbound_total_ytd`, `wht_outbound_total_ytd`
- `upcoming` — the next 10 open / overdue obligations sorted by
  due date with `days_until_due` (negative for overdue)

The `as_of_date` parameter (defaults to today) controls the overdue
calculation for `OPEN` obligations.

### 3.9 Audit trail (T23)

`TaxAuditTrailService.list_events(filter_dto)` is a thin facade over
`AuditService` that:

- gates on `taxation.audit.view`
- forces `module_code = "taxation"`
- accepts `event_type_code`, `entity_type`, `entity_id`,
  `actor_user_id`, `from_date`, `to_date`, `limit`, `offset`
- enforces `1 ≤ limit ≤ 1000` and `from_date ≤ to_date`

UI surfaces consume the returned list of `AuditEventDTO` directly.

### 3.10 Tax return PDF export (T24)

`TaxReturnPDFExportService.export(company_id,
ExportTaxReturnPDFCommand(return_id, output_path))` renders a
single-page A4 PDF containing:

- company header (display name + NIU)
- return metadata (id, status, period, filed timestamp, OTP and
  external references)
- box-level breakdown table
- totals (due / paid / outstanding)
- optional notes block

Rendering uses Qt's `QPrinter` + `QTextDocument` pipeline via
`PrintEngine.render_pdf` — no external PDF dependency. The output
path must end in `.pdf`. Audit event `TAX_RETURN_EXPORTED_PDF` is
recorded on success.

---

## 4. Validation and error handling

All services raise the standard platform exceptions:

- `ValidationError` — bad input (date range, year out of range,
  missing required field)
- `NotFoundError` — entity not found within company scope
- `ConflictError` — uniqueness / state-transition conflict
- `PermissionDeniedError` — caller lacks the required permission
- `PeriodLockedError` — posting blocked by a closed fiscal period

UI catches these and surfaces friendly messages. Database-level
exceptions are not leaked to the user.

---

## 5. Idempotency and safety

- Obligation generators (T4, T18-T21) are idempotent on
  `(company_id, tax_type_code, period_start, period_end)`.
- Customs duty rejects same-day duplicate declarations with
  `ConflictError` since `period_start == period_end == declaration_date`.
- Settlement posting is one-shot: a return with
  `journal_entry_id IS NOT NULL` cannot be re-settled.
- DSF export is read-only against accounting data — it never mutates
  posted facts.

---

## 6. Slice index

| Slice | Title                                                | Status |
|-------|------------------------------------------------------|--------|
| T1    | Constants and tax-type codes                         | Done   |
| T2    | Company tax profile (model + service + UI)           | Done   |
| T3    | Posted tax lines and tax-fact service                | Done   |
| T4    | Tax obligation calendar (VAT + CIT)                  | Done   |
| T5    | DSF Excel export — base sheets                       | Done   |
| T6    | Tax return drafting (VAT box mapping)                | Done   |
| T7    | Tax return filing                                    | Done   |
| T8    | Tax payment recording                                | Done   |
| T9    | DSF fiches and OHADA integration                     | Done   |
| T10   | Tax compliance UI page                               | Done   |
| T11   | Tax compliance dialogs (draft / file / pay)          | Done   |
| T12   | Ribbon + command palette                             | Done   |
| T13   | Withholding tax certificate register                 | Done   |
| T14   | DSF withholding sheet integration                    | Done   |
| T15   | Tax settlement service                               | Done   |
| T16   | Tax payment journal posting (bank side)              | Done   |
| T17   | Settle VAT return UI dialog                          | Done   |
| T18   | Monthly withholding obligation generator             | Done   |
| T19   | Annual Patente obligation generator                  | Done   |
| T20   | Monthly TSR obligation generator                     | Done   |
| T21   | Per-declaration customs duty obligation              | Done   |
| T22   | Tax compliance dashboard service                     | Done   |
| T23   | Tax audit trail service                              | Done   |
| T24   | Tax return PDF export service                        | Done   |
| T25   | DSF standalone P&L and Balance Sheet sheets          | Done   |
| T26   | Tax module documentation (this file)                 | Done   |

---

## 7. Operational notes for ops / support

- **Backups**: the taxation module relies entirely on the shared
  accounting database — back up the whole database; there are no
  separate stores.
- **Migrations**: Alembic migrations carry every schema change. T22-T25
  added no new tables (they reuse `tax_obligations`, `tax_returns`,
  `tax_payments`, `withholding_tax_certificates`, and the audit log);
  only the RBAC catalog was extended (`taxation.dashboard.view`,
  `taxation.audit.view`, `taxation.returns.export_pdf`). Re-run
  permission seeding after deploy so existing tenants pick up the new
  permissions.
- **Test suite**: `python -m pytest tests/test_slice_t*_*.py` covers
  the taxation slices; the full suite is the regression gate.

---

## 8. Known deferrals

- Per-tax-type UI generators for T18-T21 (Withholding / Patente / TSR /
  Customs) are not yet on the `TaxCompliancePage` ribbon. Generators
  are reachable via service calls / scripts / the Generate Calendar
  bulk action. A consolidated UI surface is scheduled for a later
  slice.
- The dashboard service has been wired but the dashboard *widget*
  surface (sparklines, cards) is to be added when the broader shell
  dashboard receives its taxation tile.
- The taxation audit page is service-only at present; UI integration is
  deferred to the same slice that adds shared audit-page primitives.

---

*Last updated: post-T26 closure.*
