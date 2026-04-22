
## Plan: Strategic Wizard System — "Intelligence #1" Shadow Advisor

**TL;DR** — Build a unified wizard framework across Seeker Accounting where every wizard is backed by a silent "expert in the shadows": it pre-fills from context, detects missing prerequisites, proposes safe defaults, previews accounting impact before commit, and explains what will happen in plain language. Wizards are not just multi-step forms — they are service-driven, stateful, resumable, idempotent orchestrations that own cross-module setup or cross-entity workflows UI dialogs should not.

---

### The "Intelligence #1" capability layer (shared by every wizard)

Every wizard gets these assistive capabilities from a shared `AssistantEngine`:

1. **Context sniffing** — active company, fiscal period, user role, last-used values, recent documents, open balances, pending tasks.
2. **Prerequisite detection** — scans required masters/mappings before starting (e.g., "VAT account role unmapped", "No open period for date X") and offers inline one-click fixes.
3. **Pattern learning (local, per-company)** — remembers: "supplier X usually posts to account 6110 with TVA 19.25%"; "this employee usually has these components"; "user always books rent on day 1".
4. **Safe defaults** — proposes values the user can accept with Enter; never silently commits them.
5. **Risk & anomaly flags** — "amount 12× the median for this supplier", "date in locked period", "duplicate invoice number for this supplier in last 90 days", "draft already exists for this period".
6. **Accounting preview** — shows the exact debits/credits a step will generate, before posting.
7. **Impact summary** — "this will open period 2026-05, generate 3 journal entries, affect 5 control accounts, lock asset #A-0142".
8. **Plain-language explain-this** — toggle that narrates *why* a field matters, not just *what* it is.
9. **Resumability** — wizards persist state so a user can stop and resume (critical for payroll run, year-end close).
10. **Dry-run mode** — every wizard that posts supports a validated preview pass before commit.

---

### Wizard catalog (grouped by domain, ordered by leverage)

#### A. Onboarding & setup (highest leverage — touched once per company)

1. **Company Setup Wizard** — create company → country/currency → fiscal calendar → COA template (OHADA variant) → opening date → default journals → document sequences → tax codes → role mappings. Shadow advisor validates coherence (e.g., presentation currency vs. country default) and seeds minimal viable configuration.
2. **Opening Balances Wizard** — per module (GL, AR, AP, inventory, fixed assets, cash/bank). Enforces that totals reconcile to the suspense/opening-equity account; detects imbalances and proposes the plug line. Prevents double-entry mistakes when migrating.
3. **Chart of Accounts Customization Wizard** — start from OHADA seed → guided add/rename/deactivate → role mapping check (AR control, AP control, VAT in/out, retained earnings, rounding, bank clearing). Advisor flags unmapped roles that would block posting later.
4. **User & Role Provisioning Wizard** — add users → assign roles → grant company access → optional permission overrides → preview effective permissions.
5. **Document Numbering Wizard** — configure prefixes, resets, per-journal sequences; advisor checks for collisions with existing posted documents.
6. **Tax Regime Wizard** — declare VAT profile, withholding profile, tax codes in use, mapping to accounts; advisor validates each code has both input/output accounts where relevant.
7. **Bank & Cash Setup Wizard** — create financial accounts → link GL accounts → opening balance → statement import format profile.
8. **Payroll Activation Wizard** — departments → positions → component library (seed or custom) → rule sets/brackets → GL mapping → first payroll period.
9. **Fixed Assets Activation Wizard** — categories → depreciation methods → GL mappings → import existing assets with NBV.
10. **Inventory Activation Wizard** — UoM categories → item categories → locations → costing method → opening stock count.

#### B. Import & migration

11. **Universal Import Wizard (per entity)** — map file → preview → validate → dry-run → commit, with canonical template always available internally. Shadow advisor auto-maps columns by header similarity and remembers mappings per company.
12. **Opening Trial Balance Import Wizard** — specialized: enforces balanced TB, proposes opening-equity plug, warns on unmapped accounts.
13. **Legacy System Migration Wizard** — orchestrates masters → openings → historical documents (optional, as memoranda) in correct order; tracks progress so users can pause.

#### C. Transactional (daily ops, but benefit from guided path for complex cases)

14. **New Customer / Supplier Wizard** — party basics → tax/withholding profile → payment terms → default GL overrides → credit limit → advisor suggests supplier group based on name/activity and checks for duplicates (fuzzy match on name, tax ID).
15. **New Item Wizard** — category → UoM → costing → tax defaults → GL mapping → optional opening stock.
16. **Recurring Transaction Wizard** — define template (rent, subscription, loan installment) → schedule → posting rules → advisor shows a 12-month forecast of entries and cash impact.
17. **Complex Sales Invoice Wizard** — multi-currency, multi-tax, with withholding/retention, advance application; advisor walks through WHT, prompts to apply customer advances, previews aging bucket impact.
18. **Supplier Bill & 3-Way-Match Wizard** — bill ↔ PO ↔ GRN; advisor highlights variances and proposes acceptance or dispute.
19. **Payment Run Wizard (AP)** — select due bills → apply priority rules → propose payment batch → review cash impact → generate payments (drafts) → post.
20. **Receipt Allocation Wizard** — unallocated receipt → list open invoices → auto-suggest allocation by reference/amount/date → apply.
21. **Credit Note / Refund Wizard** — pick source doc → reason → partial/full → impact on aging & tax → post.
22. **Expense Claim Wizard** — employee picks category → receipt → tax split → advisor suggests GL from history → routes for approval.

#### D. Period operations & close (enormous value — where accountants live)

23. **Month-End Close Wizard** — checklist-driven: unposted drafts → bank recs → control account reconciliations → accruals/prepayments → depreciation run → inventory revaluation → FX revaluation → tax reports → interim TB review → lock period. Advisor surfaces every blocker with a one-click jump.
24. **Year-End Close Wizard** — full close + P&L appropriation → retained earnings → opening balance rollover → new fiscal year setup → archive.
25. **Period Reopen Wizard** — controlled, audited; requires reason, permission, lists every entity that becomes mutable again.
26. **Accruals & Prepayments Wizard** — define accrual/prepayment → schedule reversal or amortization → advisor shows the resulting 12-period journal strip.
27. **FX Revaluation Wizard** — pick date → accounts in scope → rate source → preview P&L → post.
28. **Depreciation Run Wizard** — pick period → preview per-asset charge → exclude/hold assets → post run.
29. **Provisions & Impairment Wizard** — bad debt, inventory, asset impairment — evidence → calculation method → approval → post.

#### E. Reconciliation

30. **Bank Reconciliation Wizard** — import/load statement → auto-match by amount/date/ref → assistive matching for remainders → create missing items → finalize.
31. **Control Account Reconciliation Wizard** — AR/AP control vs. subledger; advisor lists variances line-by-line with probable causes (unposted doc, direct GL entry, period mismatch).
32. **Intercompany Reconciliation Wizard** — when multi-company is used; pair & net balances.
33. **Inventory Stock Count Wizard** — freeze → count sheet → variances → approval → adjustment posting with costing impact preview.
34. **Fixed Assets Verification Wizard** — physical verification → status updates → disposal/transfer → impairment flags.

#### F. Correction & reversal (safety-critical)

35. **Journal Correction Wizard** — find entry → reason → reverse / reverse-and-replace / adjust in current period (if source is locked); audit trail enforced.
36. **Document Void / Cancel Wizard** — void draft vs. cancel posted (with reversal); advisor explains downstream effects (allocations, stock, tax).
37. **Asset Disposal Wizard** — proceeds → calc gain/loss → tax impact → post retirement.
38. **Employee Offboarding Wizard** — final payroll → leave payout → settlement → access revocation.

#### G. Reporting & analysis

39. **Financial Statement Designer Wizard** — pick template (OHADA BS / P&L / cash flow) → verify account mappings → comparatives → preview → save.
40. **VAT Return Wizard** — period → compute boxes → reconcile to GL control → export declaration → post settlement entry.
41. **Withholding Tax Return Wizard** — similar pattern.
42. **Budget Build Wizard** — method (zero-based / prior-year ± / driver-based) → populate → approve → lock version.
43. **Cash Flow Forecast Wizard** — horizon → seed from AR/AP aging + recurring → what-if scenarios.
44. **Management Pack Wizard** — select KPIs → period → distribution list → generate PDF pack.

#### H. Payroll (deep, multi-step, high error cost)

45. **Employee Hire Wizard** — personal → contract → compensation components → tax/social security profile → bank → first-period proration. Advisor validates legal minima and duplicates.
46. **Compensation Change Wizard** — effective date → components → retro calculation → approval → payroll-run inclusion.
47. **Payroll Run Wizard** — period → employees in scope → inputs (OT, leave, bonuses) → compute → variance vs. prior period (advisor flags outliers >X%) → approve → post → payslips.
48. **Leave & Absence Wizard** — request/record → balance check → payroll impact preview.
49. **Year-End Payroll Wizard** — annual declarations, tax certificates, reconciliation to GL.

#### I. Projects / job costing / contracts

50. **Project Setup Wizard** — WBS → budget → billing rules → cost allocation rules.
51. **Revenue Recognition Wizard** — pick method (milestone, %-complete, straight-line) → schedule → post recognition entries.
52. **Project Close Wizard** — final costs → WIP clearance → margin → archival.

#### J. Governance

53. **License / Activation Wizard** — already partially present; expand to health-check and renewal.
54. **Backup & Restore Wizard** — scheduled or on-demand; integrity check.
55. **Audit Export Wizard** — date range → entities → package for external auditor.

---

### Architecture — how wizards should be built (non-negotiable)

- **`platform/wizards/`** — framework: `WizardBase`, `WizardStep`, `WizardController`, `WizardState` (serializable), `WizardHost` dialog, navigation, validation hook, preview panel, advisor panel.
- **Service-driven steps** — each step calls services only (UI → service → repo). Steps are pure orchestration; no SQL, no direct model writes.
- **State machine** — explicit states: `draft → validated → previewed → committing → committed | failed`. Persist to a `wizard_runs` table for resumability and audit.
- **Idempotent commit** — wizards that post must be replay-safe; use a correlation id so retries never double-post.
- **Pluggable Advisor** — `AssistantEngine` exposes `suggest(context)`, `validate(step, payload)`, `anomalies(payload)`, `preview(payload)`. Per-wizard advisors register rules; a shared rule library covers common checks (period lock, role mapping, duplicate detection, tolerance bands).
- **Telemetry (local)** — wizard completion rates, step-level abandonment, advisor suggestion acceptance — to improve defaults over time.
- **Permission-aware** — every wizard declares required permissions; steps that cross boundaries (reopen period, void posted doc) require elevated confirmation.
- **Accessibility & keyboard-first** — Enter to accept suggestion, Alt+N next, Alt+P previous, Ctrl+S save-and-resume.

---

### Relevant existing areas to reuse (reference only)

- platform — host for the new `wizards/` package
- companies — target for Company Setup Wizard
- accounting — close / period / journal correction wizards
- payroll — payroll run, hire, year-end
- fixed_assets — acquisition, disposal, depreciation run
- treasury — bank rec, payment run
- sales, modules/purchases — document + allocation wizards
- inventory — stock count, opening stock
- reporting — VAT/WHT return, statement designer

---

### Decisions proposed (for your review)

- **Framework first, wizards second** — build `platform/wizards/` + `AssistantEngine` as Slice W0 before any domain wizard. One wizard done right seeds all the rest.
- **First three wizards to ship (highest leverage, proves the pattern):**
  1. Company Setup Wizard (also the new-company onboarding path)
  2. Month-End Close Wizard (daily accountant pain)
  3. Payroll Run Wizard (multi-step, advisor shines via variance detection)
- **Advisor is local-only** — no cloud/LLM in the core loop; deterministic rules + learned per-company patterns stored in SQLite. LLM hooks can be added later as an optional enrichment.
- **Wizards persist state** — `wizard_runs` table added via Alembic; resumable close/payroll flows require this.
- **Wizards never bypass services** — an important guardrail aligned with CLAUDE.md.

---

### Further considerations (please weigh in)

1. **Scope of first delivery** — (a) framework + 1 flagship wizard (Company Setup), (b) framework + 3 flagship wizards, (c) framework only with 2 thin proof-of-concept wizards. *Recommend (a)* to de-risk the framework with real use.
2. **Advisor intelligence depth** — (a) rules-only (deterministic, fast, explainable), (b) rules + per-company pattern learning (local stats), (c) rules + patterns + optional LLM narration. *Recommend (b)* — maximum leverage, fully offline, no external dependencies.
3. **Wizard resumability storage** — (a) dedicated `wizard_runs` table, (b) reuse audit/import-job infrastructure, (c) in-memory only for v1. *Recommend (a)* — small, clean, auditable.
4. **Entry points** — (a) command palette + module pages, (b) a dedicated "Assistant" sidebar panel that surfaces relevant wizards by context, (c) both. *Recommend (c)* — the Assistant panel is where Intelligence #1 lives visibly.
5. **Priority ordering beyond the first 3** — want a ranked roadmap next, or decide per slice?

---

Tell me which direction to refine: narrow the first wave, go deeper on the advisor engine, lock the framework design, or reorder priorities — then I'll tighten the plan accordingly.