# Chart of Accounts Customization Wizard

## Purpose

Turn the current chart-of-accounts setup flow from a collection of separate actions:

- `Seed OHADA`
- `Import Template`
- `New Account`
- `Edit Account`
- `Deactivate`
- `Role Mappings`

into one guided, intelligent wizard launched from the chart ribbon.

This wizard should feel like an accounting architect sitting beside the user:

- it inspects the current company chart first
- it recommends a safe baseline
- it guides structural changes by business area
- it includes account-role mapping inside the same flow
- it warns about configuration gaps that would block posting later

This is not just a multi-step form. It is a chart analysis, planning, and commit workflow.

---

## Existing Foundations We Should Reuse

The wizard should be built on top of what already exists, not beside it.

- Ribbon entry and command routing already exist in [ribbon_registry.py](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/app/shell/ribbon/ribbon_registry.py:359>) and [chart_of_accounts_page.py](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/modules/accounting/chart_of_accounts/ui/chart_of_accounts_page.py:536>)
- OHADA seed logic already exists in [chart_seed_service.py](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/modules/accounting/chart_of_accounts/services/chart_seed_service.py:1>)
- built-in template preview/import logic already exists in [chart_template_import_service.py](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/modules/accounting/chart_of_accounts/services/chart_template_import_service.py:1>)
- the built-in OHADA resource already exists in [ohada_syscohada_v1.csv](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/resources/chart_templates/ohada_syscohada_v1.csv:1>)
- account CRUD and validation already exist in [chart_of_accounts_service.py](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/modules/accounting/chart_of_accounts/services/chart_of_accounts_service.py:1>)
- account-role mapping logic already exists in [account_role_mapping_service.py](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/modules/accounting/reference_data/services/account_role_mapping_service.py:1>)
- guided missing-mapping resolution already exists in [error_resolution_resolver.py](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/platform/exceptions/error_resolution_resolver.py:258>)

The wizard should orchestrate these services, not replace them.

---

## Core Product Idea

### Entry point

Add a new primary ribbon command on the chart surface:

- `chart_of_accounts.wizard`
- label: `Customize Chart`
- placement: before `Seed OHADA`
- variant: `primary`

It should launch a large guided window from the chart ribbon.

### When the wizard should be used

The wizard is best for:

- first-time chart setup after company creation
- bringing an incomplete chart up to posting-ready state
- adding missing OHADA structure safely
- cleaning or standardizing a manually-curated chart
- mapping required roles without waiting for posting errors later

Manual `New Account` and `Edit Account` should remain for expert direct work.
The wizard becomes the safe, recommended path.

---

## Wizard Modes

The first screen should detect the current company state and recommend a mode.

### 1. Empty Chart Mode

Shown when the company has no accounts.

Recommended action:

- seed OHADA baseline
- review recommended roles
- finish mapping and readiness checks

### 2. Existing Chart, Incomplete Mode

Shown when accounts exist but the chart has obvious gaps.

Examples:

- missing role mappings
- no bank account mapped
- no receivables/payables control account mapped
- payroll payable or inventory control missing for active modules
- current chart only partially overlaps OHADA baseline

Recommended action:

- compare current chart to OHADA template
- add missing structure only
- map critical roles
- validate posting readiness

### 3. Existing Curated Chart Mode

Shown when the company already has a substantial chart.

Recommended action:

- skip seeding unless user explicitly wants add-missing baseline
- focus on rename, deactivate, create, and map
- run readiness and anomaly scan

### 4. Repair / Mapping-Only Mode

Shown when the chart itself is acceptable but posting blockers exist.

Recommended action:

- jump almost directly to role mapping and readiness checks

---

## Recommended Step Flow

## Step 1. Scan And Explain

This is the wizard’s intelligence anchor.

Show:

- active company
- account count
- top-level class coverage
- OHADA overlap estimate
- missing recommended accounts
- missing required role mappings
- suspicious chart conditions

Examples of findings:

- `AR Control` not mapped
- `AP Control` not mapped
- no likely bank settlement account found
- class 44 tax accounts exist but no VAT mapping candidate has been approved
- control account is marked manual-posting
- parent accounts are active but no posting leaf exists in a business area
- duplicate-like account names or code patterns

Each finding should have:

- severity: blocker, caution, suggestion
- affected workflow: sales posting, purchase posting, treasury, payroll, year-end
- action link: `Fix in wizard`
- explanation: `Why this matters`

---

## Step 2. Baseline Strategy

This step decides how the current chart should relate to OHADA.

Choices:

- `Seed OHADA baseline into empty chart`
- `Add only missing OHADA accounts to current chart`
- `Keep current chart structure and customize manually`
- `Import external chart file first, then validate`

Advisor recommendation rules:

- if chart is empty, recommend OHADA seed
- if chart exists but clearly partial, recommend add-missing OHADA
- if chart is large and internally consistent, recommend keep current chart
- if import file is present, preview before commit and show conflict count

This step should reuse `preview_import()` and `seed_built_in_chart()` instead of re-implementing seed logic.

---

## Step 3. Guided Structure Customization

This is where the wizard becomes easy to use.

Do not force users to work only from one huge account tree.
Group work by business area:

- Equity and year-end
- Sales and receivables
- Purchases and payables
- VAT and taxes
- Treasury and cash
- Inventory
- Payroll
- Projects and contracts
- Miscellaneous adjustments

For each area, show a diff-style workbench:

- recommended accounts from baseline
- current matching accounts
- missing accounts
- inactive accounts
- custom accounts in that area

Available actions:

- `Add recommended`
- `Rename`
- `Create sibling`
- `Create child`
- `Deactivate`
- `Keep as-is`
- `Mark as custom`

Important rule:

- never delete accounts from the wizard
- use deactivate, not destructive removal

For accounts with history, the wizard should warn:

- `This account has posted history; deactivation is safe, but replacement mapping should be confirmed`

---

## Step 4. Mapping Wizard

This is part of the same flow, not a separate afterthought.

The user asked for this to go deep, and it should.

### 4.1 Role groups

Split mapping into clear groups:

- Core posting: `AR Control`, `AP Control`, `Sales Revenue`, `Purchases Expense`
- Treasury: `Main Bank`, `Cash On Hand`, `Petty Cash`, `Bank Clearing`
- Inventory: `Inventory Control`
- Payroll: `Payroll Payable`
- Tax: `VAT Input`, `VAT Output`
- Equity / close: `Retained Earnings`
- Precision: `Rounding Gain`, `Rounding Loss`
- Project roles: existing project role set

### 4.2 Requirement levels

Each role needs a requirement level:

- `blocker`
- `recommended`
- `optional`

Examples:

- `AR Control`: blocker if sales is active
- `AP Control`: blocker if purchases is active
- `VAT Input` / `VAT Output`: blocker if VAT is enabled or VAT tax codes are active
- `Retained Earnings`: blocker for year-end close, caution otherwise
- `Bank Clearing`: recommended if treasury reconciliation/import is used
- `Rounding Gain` / `Rounding Loss`: recommended when foreign currency, tax-inclusive pricing, or invoice adjustments are used

The wizard should not treat every missing role equally.

### 4.3 Intelligent recommendations

For each role, show ranked account candidates with confidence:

- `High confidence`
- `Medium confidence`
- `Low confidence`

Each recommendation must show why:

- `Code starts with 411`
- `Name contains CLIENTS / RECEIVABLES`
- `Account type is current asset`
- `Account is already marked control account`
- `Code is in OHADA class 44 and name suggests VAT collected`

One-click actions:

- `Accept recommendation`
- `Choose another account`
- `Clear mapping`
- `Skip for now`

### 4.4 Mapping flags

This should be explicit in the design.

We need a mapping-intelligence layer, not just free-form heuristics.

Recommended implementation:

Add a wizard metadata resource for the OHADA template, for example:

- `resources/chart_templates/ohada_syscohada_v1_role_hints.json`

This metadata should define:

- likely role code(s)
- business area
- confidence
- module scope
- whether a role is canonical for that code
- whether the account is usually a parent or posting leaf

Example uses:

- `411...` accounts likely candidates for `ar_control`
- `401...` accounts likely candidates for `ap_control`
- `445...` accounts likely candidates for VAT input/output roles
- `52...` accounts likely candidates for `bank_main` or `bank_clearing`
- `11...` or retained earnings structure candidates for `retained_earnings`

This gives the wizard explainable intelligence without needing an LLM.

---

## Step 5. Posting-Readiness Check

This step answers the real question:

`If the user leaves the wizard now, what will still break later?`

The wizard should run a readiness report with categories:

- posting blockers
- statutory/tax cautions
- structural cautions
- cleanup suggestions

### Blockers

- required account role mapping missing
- mapped account inactive
- mapped account belongs to wrong company
- mapped account unsuitable for control use
- no active company chart

### Structural cautions

- control account marked `allow_manual_posting=True`
- inactive child structure under an active parent business area
- obvious duplicate account names or redundant leafs
- account code conflicts with OHADA numbering expectation

### Downstream cautions

- VAT chart looks ready but tax-code account mappings are still incomplete
- treasury accounts exist but financial account → GL mapping is incomplete
- payroll roles are missing while payroll is activated

This step should include deep links:

- `Open Tax Codes`
- `Open Financial Accounts`
- `Open Payroll Setup`
- `Return to this wizard later`

---

## Step 6. Summary And Commit

Do not commit changes step-by-step invisibly.

Show an operation summary first:

- accounts to create
- accounts to rename
- accounts to deactivate
- role mappings to create/update/clear
- warnings to carry forward

Then let the user:

- `Apply All`
- `Save Draft / Resume Later`
- `Export Review`
- `Cancel`

Commit should be transactional.

If anything fails:

- keep the plan
- show what failed
- do not leave the chart half-mutated

---

## Intelligence Rules

The wizard should feel smart because it is context-aware and explainable.

## A. Company-context rules

Read:

- active company
- base currency
- whether sales, purchases, payroll, inventory, treasury, projects are active or already used
- current role mappings
- existing tax codes
- existing financial accounts

## B. Chart-shape rules

Use:

- code prefixes
- account type
- account class
- parent-child location
- manual posting flag
- control flag
- active flag
- name patterns

## C. Recommendation scoring

Each candidate score can be built from:

- code match strength
- name match strength
- type compatibility
- class compatibility
- control/manual-posting suitability
- role-hint metadata match

## D. Explainability

Every recommendation should answer:

- `Why was this suggested?`
- `Why is this a blocker?`
- `What workflows depend on this mapping?`

---

## Role Catalog Expansion Needed

Current `ACCOUNT_ROLE_DEFINITIONS` in [account_role_codes.py](</c:/Users/User/Desktop/Seeker Accounting/src/seeker_accounting/modules/accounting/reference_data/constants/account_role_codes.py:1>) do not yet cover the full wizard scope.

Add at least:

- `vat_input`
- `vat_output`
- `retained_earnings`
- `bank_clearing`
- `rounding_gain`
- `rounding_loss`

Possibly later:

- `vat_credit_carryforward`
- `exchange_gain_realized`
- `exchange_loss_realized`

Without this expansion, the wizard cannot fully guard the later workflows the user wants protected.

---

## Proposed Service Layer

## 1. `ChartCustomizationWizardService`

Purpose:

- orchestrate scan, recommendation, and commit plan generation

Suggested methods:

- `analyze_chart(company_id) -> ChartWizardAnalysisDTO`
- `build_plan(company_id, selections) -> ChartWizardPlanDTO`
- `apply_plan(company_id, plan, correlation_id) -> ChartWizardApplyResultDTO`

## 2. `ChartRoleRecommendationService`

Purpose:

- compute ranked account candidates for each role

Suggested methods:

- `recommend_role_candidates(company_id) -> list[RoleRecommendationDTO]`
- `score_candidate(role_code, account) -> CandidateScoreDTO`

## 3. `ChartReadinessService`

Purpose:

- run blocker/caution checks before and after plan generation

Suggested methods:

- `evaluate_chart_readiness(company_id) -> ChartReadinessDTO`

## 4. `ChartTemplateRoleHintLoader`

Purpose:

- load deterministic hint metadata from resource files

This keeps the intelligence versioned and explainable.

---

## Suggested DTOs

- `ChartWizardAnalysisDTO`
- `ChartWizardIssueDTO`
- `ChartWizardAreaDTO`
- `ChartWizardRecommendationDTO`
- `RoleRecommendationDTO`
- `RoleCandidateDTO`
- `ChartWizardPlanDTO`
- `ChartWizardOperationDTO`
- `ChartWizardApplyResultDTO`
- `ChartReadinessDTO`

These should be domain DTOs, not UI widgets carrying state.

---

## UI / UX Shape

The wizard should not look like a generic survey.

Recommended layout:

- left: step rail
- center: active work surface
- right: advisor panel
- bottom: summary / next / back / apply

The advisor panel should show:

- current step guidance
- recommendations
- cautions
- `Why?`

The center surface changes by step:

- scan dashboard
- OHADA diff view
- grouped account editor
- mapping matrix
- readiness report
- commit preview

Keyboard-first behavior:

- Enter accepts best recommendation
- space toggles a suggested change
- Ctrl+S saves draft
- Alt+N next step
- Alt+P previous step

---

## Integration With Existing Chart Page

The chart page should keep the current direct actions, but the wizard becomes the preferred high-level action.

Recommended ribbon/button order:

- `Customize Chart`
- `New Account`
- `Edit Account`
- `Deactivate`
- `Seed OHADA`
- `Import Template`
- `Role Mappings`

In empty state, the primary CTA should become:

- `Start Chart Wizard`

not just `Seed Built-In OHADA Chart`

---

## Safe Commit Rules

- no physical account deletion
- deactivation only
- commit all selected actions in one transaction
- if plan includes both chart mutations and role mappings, apply together
- preserve audit trail for every account mutation and role mapping change
- if a role maps to an inactive account, reject commit
- if deactivation would orphan active children, reject commit

---

## Suggested Rollout

## Slice 1. Smart Ribbon Entry + Scan

- add ribbon command
- launch wizard shell
- scan current chart
- show missing roles and recommended next action

## Slice 2. Baseline And Diff

- wire OHADA preview/add-missing mode
- show grouped missing-account recommendations

## Slice 3. Mapping Wizard

- expand role catalog
- build candidate ranking
- apply mapping changes from inside wizard

## Slice 4. Readiness And Commit

- add blocker/caution report
- build transactional apply plan

## Slice 5. Resume / Draft

- save wizard runs
- allow resume from ribbon

---

## Recommendation

Do this as the first serious wizard in Seeker.

Why:

- the accounting foundation already exists
- the user pain is clear
- it reuses real services that are already in the codebase
- it prevents later posting failures instead of reacting to them
- it establishes the quality bar for every later wizard

The key product rule should be:

`The wizard does not ask the user to know the chart.`

It studies the chart first, then proposes the safest next moves.
