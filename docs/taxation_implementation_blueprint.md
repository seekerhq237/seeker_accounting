# Taxation Implementation Blueprint

## Context

This note synthesizes:

- the current Seeker Accounting codebase
- the Cameroon tax documents provided locally
- a light verification pass against current official DGI/CNPS publications on 2026-04-21

The goal is to define how taxation should be implemented in Seeker in a way that is:

- configuration-driven
- effective-dated
- company-scoped
- journal-linked
- filing-aware
- practical for a desktop accounting system

## What Already Exists In The Codebase

Seeker already has two useful taxation foundations.

### 1. Payroll taxation is already much more advanced than the rest

The payroll module already contains Cameroon-specific engines and statutory setup for:

- IRPP and CAC
- TDL
- CNPS employee and employer pension
- FNE employee and employer
- family allowances
- accident risk classes
- payroll remittance tracking

Relevant code:

- `src/seeker_accounting/modules/payroll/engines/irpp_engine.py`
- `src/seeker_accounting/modules/payroll/engines/cnps_engine.py`
- `src/seeker_accounting/modules/payroll/engines/tdl_engine.py`
- `src/seeker_accounting/modules/payroll/engines/salary_deductions_engine.py`
- `src/seeker_accounting/modules/payroll/engines/employer_contribution_engine.py`
- `src/seeker_accounting/modules/payroll/services/payroll_calculation_service.py`
- `src/seeker_accounting/modules/payroll/statutory_packs/cameroon_default_pack.py`
- `src/seeker_accounting/modules/payroll/services/payroll_remittance_service.py`
- `src/seeker_accounting/modules/payroll/services/payroll_remittance_deadline_service.py`

Conclusion: payroll tax should be treated as a strong existing foundation, not a greenfield feature.

### 2. Transaction tax exists, but only as a generic first-pass layer

The accounting side already has:

- effective-dated `tax_codes`
- `tax_code_account_mappings`
- tax code selection on sales invoice lines and purchase bill lines
- tax posting to tax liability and tax asset accounts

Relevant code:

- `src/seeker_accounting/modules/accounting/reference_data/models/tax_code.py`
- `src/seeker_accounting/modules/accounting/reference_data/models/tax_code_account_mapping.py`
- `src/seeker_accounting/modules/accounting/reference_data/services/tax_setup_service.py`
- `src/seeker_accounting/modules/sales/services/sales_invoice_service.py`
- `src/seeker_accounting/modules/sales/services/sales_invoice_posting_service.py`
- `src/seeker_accounting/modules/purchases/services/purchase_bill_service.py`
- `src/seeker_accounting/modules/purchases/services/purchase_bill_posting_service.py`

Conclusion: Seeker has a tax setup base, but not yet a tax compliance module.

## Important Gaps Found In The Current Implementation

These are the main gaps we should design around.

### 1. Only one tax code can be stored per transaction line

Current sales and purchase lines only store:

- `tax_code_id`
- `line_tax_amount`

That is too limited for Cameroon once we need combinations such as:

- VAT + excise
- VAT + withholding
- recoverable and non-recoverable tax behavior
- special industry taxes

Relevant models:

- `src/seeker_accounting/modules/sales/models/sales_invoice_line.py`
- `src/seeker_accounting/modules/purchases/models/purchase_bill_line.py`

### 2. Recoverability is stored but not used

`tax_codes.is_recoverable` exists, but it is not used in calculation or posting logic.

Today, purchase tax is effectively treated as recoverable whenever a tax asset account is mapped.

This is not enough for:

- blocked input VAT
- non-deductible VAT
- taxes that must be expensed instead of capitalized as tax recoverable

### 3. Tax inclusive behavior exists as a company preference but is not wired into documents

`tax_inclusive_default` exists at company preference level, but I did not find it used in sales or purchase calculations.

That means the system currently behaves like a tax-exclusive engine only.

### 4. Sales and purchases do not enforce tax rules consistently

`SalesInvoiceService` validates tax code effective dates and supports:

- `PERCENTAGE`
- `FIXED_AMOUNT`
- `EXEMPT`

`PurchaseBillService` currently does not mirror that logic. It directly multiplies subtotal by `rate_percent` and does not apply the same effective-date or method handling.

This should be unified before broader tax work starts.

### 5. Tax account mappings are only partially used

`tax_code_account_mappings` stores:

- `sales_account_id`
- `purchase_account_id`
- `tax_liability_account_id`
- `tax_asset_account_id`

But the current posting services only use the liability and asset accounts. The sales and purchase account mapping fields are not driving posting behavior.

### 6. There is no tax return, filing, or settlement domain outside payroll

Missing today:

- monthly VAT return workflow
- excise declaration workflow
- corporate income tax installment tracking
- annual corporation tax balance tracking
- tax obligation calendar
- tax payment register tied to returns
- withholding certificates / evidence register
- DSF export/generation
- filing status tracking

### 7. Company tax identity is too light for compliance workflows

Company setup currently stores NIU and CNPS employer number, but not enough tax profile data to drive compliance safely.

Missing examples:

- tax center / filing segment
- tax regime
- SME classification
- VAT liability start date
- DSF form family
- filing mode
- OTP participation
- default withholding status

## What The Documents Tell Us

## VAT

From the provided `FICHE TVA.pdf` and the official DGI VAT sheet:

- VAT applies to taxable operations carried out in Cameroon.
- The general rate is `19.25%`, i.e. `17.5% + 10% CAC`.
- The zero rate is used for exports.
- VAT registration is generally required from `50,000,000 FCFA` annual turnover, with some sectors attached to the real regime by default.
- VAT returns are monthly and must be filed within the first `15 days` of the following month.
- Deductible VAT depends on documentary and payment conditions.
- VAT credits may be carried forward and in some cases refunded.

Implementation impact:

- VAT cannot stay as "just one percentage field".
- We need recoverable vs non-recoverable handling.
- We need exemption and zero-rate support as first-class behavior.
- We need monthly VAT return generation from posted documents, not from draft documents.

## Corporate income tax (IS)

From `ALL ABOUT IS.pdf`, `SMES TAXESFT PME.pdf`, and the official DGI IS sheet:

- Standard corporation tax rate is `30%`.
- SMEs with turnover `<= 3,000,000,000 FCFA` benefit from `25%`.
- CAC increases the final burden by `10%`.
- Monthly installments are regime-driven and must be paid by the `15th` of the following month.
- The official material indicates the installment logic is regime-sensitive, so Seeker should not hard-code one single installment rate.
- Annual balance deadlines differ by tax segment:
  - `15 March` for large taxpayers
  - `15 April` for medium / specialized centers
  - `15 May` for divisional centers / smaller taxpayers

Implementation impact:

- We need company tax regime and filing-segment metadata.
- We need a monthly corporate tax installment register.
- We need an annual corporate tax balance workflow tied to year-end results.
- We should not try to "calculate final IS from bookkeeping only" without an adjustment layer, because taxable profit differs from accounting profit.

## IRPP on salaries

From the provided IRPP guide, the payroll blueprint, and official DGI material:

- payroll withholding is monthly
- employer remittance is due by the `15th` of the following month
- salary IRPP uses:
  - `30%` professional expense abatement
  - `500,000 FCFA` annual deduction
  - progressive brackets `10 / 15 / 25 / 35`
  - `10%` CAC
- no withholding below the practical threshold shown in DGI material for monthly salaries under `62,000 FCFA`

Implementation impact:

- the current payroll model is directionally correct
- payroll tax work should focus on hardening, validation, reporting, and filing outputs rather than replacing the engine

## DSF

From `DSF 2025 GUIDE.pdf`, `ONLINE DSF ELECTRONIC REPORTING PROCESS.pdf`, and the official DGI DSF 2025 guide:

- the guide dated `2025-03-03` states that the `2025` campaign is used to file the DSF for financial year `2024`
- the taxpayer must have a NIU first
- the DGI supports three submission modes:
  - DGI Excel upload for non-web-based accounting systems
  - direct manual entry
  - API for web-based accounting systems

Implementation impact:

- for Seeker as it exists today, Excel export is the practical first DSF target
- API submission should be treated as a later integration path
- portal automation should not be the first approach

## SME regime

From `SMES TAXESFT PME.pdf`:

- `<= 10,000,000 FCFA`: liberatory tax regime
- `10,000,000 to 50,000,000 FCFA`: simplified regime
- `>= 50,000,000 FCFA`: real regime

Implementation impact:

- company tax regime cannot be inferred lazily from a single tax code
- Seeker needs explicit company tax profile setup and possibly yearly regime history

## Excise duty

From `FICHE DA.pdf`:

- excise applies only to specific industries/products/services
- rates vary by category and can be ad valorem or specific
- excise is declared on the same monthly declaration cycle as VAT
- payment is also due by the `15th` of the following month

Implementation impact:

- excise should be an optional industry-specific layer, not forced into all companies
- the tax engine must support both percentage and specific/unit-based taxes if we ever target excise-heavy businesses

## OTP and tax registration

From the registration and OTP guides:

- NIU onboarding is a prerequisite for digital tax interactions
- OTP supports tax payments by the taxpayer or by an authorized third party through a payment-convention model

Implementation impact:

- Seeker should track NIU and filing readiness
- payment execution can remain external, but payment references and OTP evidence should be trackable inside Seeker

## Design Principles To Lock

Taxation in Seeker should follow the same discipline as payroll:

- rules must be table-driven
- all statutory logic must be effective-dated
- calculation truth and filing truth must be separate
- accounting truth must come from posted journals
- returns must be built from posted source documents plus explicit tax adjustments
- payment tracking must be separate from payment execution

## Recommended Target Architecture

## 1. Keep payroll taxation as its own bounded domain

Payroll tax is already specialized enough to remain separate from transaction tax.

Do not try to merge payroll tax into a generic tax engine.

Instead:

- keep payroll engines and statutory packs
- add stronger remittance reporting and export support
- connect payroll remittances into the broader tax calendar

## 2. Add a real transaction-tax domain

Create a taxation domain for non-payroll taxes with these subareas:

- tax setup
- tax calculation
- tax obligations / deadlines
- tax returns
- tax payments
- DSF support

Suggested module boundary:

- `src/seeker_accounting/modules/taxation/`

Core services:

- `company_tax_profile_service`
- `transaction_tax_calculation_service`
- `tax_return_service`
- `tax_obligation_service`
- `tax_payment_tracking_service`
- `dsf_export_service`

## 3. Move from single-tax-per-line to tax-detail rows

Add document-level tax detail rows so one business line can produce multiple tax consequences.

Suggested new tables:

- `sales_invoice_line_taxes`
- `purchase_bill_line_taxes`

Each row should store:

- source line id
- tax code id
- tax type
- tax basis
- tax rate snapshot
- tax amount
- recoverable flag snapshot
- declaration bucket / return box code

This lets one invoice line generate:

- VAT
- excise
- withholding
- special industry taxes

without corrupting the accounting model.

## 4. Add company tax profile and filing profile

Suggested one-to-one table:

- `company_tax_profiles`

Suggested fields:

- `company_id`
- `niu`
- `tax_center_code`
- `taxpayer_segment_code`
- `tax_regime_code`
- `is_vat_liable`
- `vat_effective_from`
- `cit_rate_profile_code`
- `cit_installment_profile_code`
- `sme_qualified_flag`
- `dsf_form_code`
- `dsf_submission_mode_code`
- `otp_enabled_flag`
- `default_withholding_applicable_flag`
- `updated_at`
- `updated_by_user_id`

This should not be mixed into `company_fiscal_defaults`. The fiscal default table is currently too small and too generic.

## 5. Add tax obligations and returns as explicit records

Suggested tables:

- `tax_obligations`
- `tax_returns`
- `tax_return_lines`
- `tax_payments`

Examples of obligation types:

- monthly VAT
- monthly excise
- monthly corporation tax installment
- monthly payroll IRPP/CNPS remittance
- annual corporation tax balance
- annual DSF

Each obligation should know:

- company
- tax type
- period start / end
- due date
- status
- linked return id
- linked payment ids

## 6. Build returns from posted ledgers plus controlled adjustments

Do not build returns from draft transaction tables.

Return generation should use:

- posted sales invoices
- posted purchase bills
- posted payroll runs
- posted treasury settlements
- explicit tax adjustment entries where needed

Typical adjustments:

- irrecoverable VAT reclass
- tax-only corrections
- prior-period carryforward
- blocked credit notes
- manual box adjustments with audit trail

## 7. Treat DSF as an annual compliance product, not just a report

DSF work should eventually include:

- company metadata validation
- form-family selection
- dataset completeness checks
- DGI Excel export
- filing-status tracking
- optional API integration later

For the desktop Seeker product, DGI Excel export is the right first target.

## Recommended Rollout

## Phase 0 - Hardening The Existing Foundation

Do this first before adding new tax modules.

1. Create a shared transaction tax calculator used by both sales and purchases.
2. Make purchase bill tax validation match sales invoice tax validation.
3. Start using `is_recoverable` in posting logic.
4. Wire `tax_inclusive_default` into document creation and calculation.
5. Audit tax code account mapping usage and either use or remove dead mapping semantics.

This phase reduces hidden inconsistency before new features multiply it.

## Phase 1 - VAT MVP

Scope:

- company tax profile
- tax codes with better semantics
- line tax detail rows
- recoverable / non-recoverable VAT
- exempt / zero-rate / standard VAT
- tax-inclusive and tax-exclusive pricing
- monthly VAT obligation generation
- draft VAT return summary built from posted transactions

This is the highest-value non-payroll tax phase.

## Phase 2 - Filing And Payment Control

Scope:

- tax calendar
- due-date dashboard
- tax return status flow
- OTP reference capture
- evidence attachment
- tax payment tracking
- journal settlement links

This turns tax from a calculation feature into an operational workflow.

## Phase 3 - Corporate Income Tax And SME Regimes

Scope:

- company regime classification
- monthly CIT installment tracking
- annual CIT balance workflow
- SME deadline logic
- minimum tax / regime-aware calculation hooks where applicable
- tax-adjustment ledger for accounting-profit to taxable-profit reconciliation

Important: the final annual IS engine should not be launched until we define a controlled tax-adjustment model.

## Phase 4 - DSF

Scope:

- DSF readiness checks
- DSF data assembly from financial statements, notes, and company profile
- DGI Excel export
- filing package archive
- optional future DGI API integration

Given the official DGI guidance, this phase should start with Excel export for Seeker.

## Phase 5 - Specialized Taxes

Only after VAT, CIT, payroll, and DSF are stable:

- excise duties
- TSR / non-resident service withholding
- rent withholding / precompte on loyer
- IRCM support if shareholder/distribution workflows are added
- dispute and payment-deferral workflows

## Concrete First Backlog I Recommend

If we start implementation soon, this is the order I would use.

1. Introduce a shared transaction tax calculation service and remove the sales/purchase mismatch.
2. Add `company_tax_profiles`.
3. Add `is_tax_inclusive` at document header level for sales and purchases.
4. Add line-tax detail tables so one line can produce several taxes.
5. Make purchase posting respect recoverability and non-recoverability.
6. Add a monthly VAT obligation generator.
7. Add a VAT return preview workspace based on posted periods.
8. Add tax payment tracking with OTP reference capture.
9. Add a DSF preparation/export service that starts with DGI Excel output.

## Practical Product Decisions

These decisions will keep the implementation realistic.

### Decision 1: Posted journals are the source of truth

Tax returns should be derived from posted accounting truth, not from editable operational screens.

### Decision 2: Filing and payment stay inside Seeker; payment execution stays outside

Seeker should track:

- what is due
- what was filed
- what was paid
- when
- by whom
- with which external reference

But it should not attempt bank execution or OTP payment execution in the first phase.

### Decision 3: Desktop Seeker should target export-first DSF support

The official DGI guide explicitly distinguishes:

- Excel upload for non-web systems
- API for web-based systems

Seeker should therefore start with export-first DSF support.

### Decision 4: Rates must never be hard-coded as product truth

The official DGI site currently shows a `CGI 2025` publication and a `Finance Law 2026` circular.
That means the product must assume tax rules can change year to year.

So:

- every rule must be effective-dated
- statutory packs or rate profiles must be versioned
- historical returns must keep snapshots

## Recommended Scope Boundaries

What should be in the first serious taxation release:

- VAT
- payroll tax hardening
- tax calendar
- tax payment tracking
- company tax profile
- DSF preparation/export

What should probably wait:

- full excise support
- automated DGI API submission
- automated CNPS submission
- full annual individual income return support for non-professional taxpayers
- litigation / deferral workflow automation

## Summary

Seeker does not need taxation to start from zero.

The right strategy is:

1. keep the current Cameroon payroll tax engine and harden it
2. upgrade the generic sales/purchase tax layer into a true transaction-tax domain
3. add filing, obligation, and payment tracking as explicit business objects
4. target VAT and DSF first, because they are the most operationally important for the current product shape

## Sources Reviewed

Local documents reviewed:

- `c:/Users/User/Downloads/Taxation documentation/FICHE TVA.pdf`
- `c:/Users/User/Downloads/Taxation documentation/ALL ABOUT IS.pdf`
- `c:/Users/User/Downloads/Taxation documentation/PERSONAL INCOME TAX (IRPP WHAT YOU NEED TO KNOW.pdf`
- `c:/Users/User/Downloads/Taxation documentation/DSF 2025 GUIDE.pdf`
- `c:/Users/User/Downloads/Taxation documentation/ONLINE DSF ELECTRONIC REPORTING PROCESS.pdf`
- `c:/Users/User/Downloads/Taxation documentation/TAX-REGISTRATION GUIDE (ATOM DGI) ONLINE.pdf`
- `c:/Users/User/Downloads/Taxation documentation/OTP Guide for paying taxes and duties by_on behalf of a third party.pdf`
- `c:/Users/User/Downloads/Taxation documentation/ONLINE PAYMENT DEFERRAL GUIDE.pdf`
- `c:/Users/User/Downloads/Taxation documentation/SMES TAXESFT PME.pdf`
- `c:/Users/User/Downloads/Taxation documentation/FICHE DA.pdf`
- `c:/Users/User/Downloads/Taxation documentation/CGI 2024 version anglaise.pdf`

Official web verification reviewed on 2026-04-21:

- DGI DSF 2025 guide: `https://impots.cm/sites/default/files/documents/GUIDE%20UTILISATEUR%20DSF%202025%20DU%2003-03-2025.pdf`
- DGI VAT sheet: `https://impots.cm/sites/default/files/documents/FICHE%20TVA.pdf`
- DGI IS sheet: `https://www.impots.cm/sites/default/files/documents/FICHE%20SUR%20L%27IS.pdf`
- DGI IRPP guidance page: `https://www.impots.cm/fr/document/tout-savoir-sur-lirpp`
- DGI homepage showing current 2026 publications: `https://impots.cm/fr`
- CNPS employer obligations page: `https://www.cnps.cm/fr/employeurs/obligations-de-lemployeur1.html`
- CNPS decree/rates PDF: `https://www.cnps.cm/images/documentutile/decret%20fixant%20taux%20de%20cotisations%20sociales%20et%20plafonds%20des%20rmunrations_baremes.pdf`
