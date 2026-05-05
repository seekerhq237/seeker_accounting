# Payroll Module — UX & Workflow Remediation Plan

Status: blueprint, pre-implementation.
Owner: payroll squad.
Source critique: see prior audit message — surfaces, wizards, workspaces, dialogs, end-to-end walkthrough, and benchmark vs. Workday / ADP / Gusto / SAP SuccessFactors / Sage Paie / Cegid Y2 / QuickBooks Payroll.

This plan turns the audit findings into a build program. It is organised as **14 phases**. Phases are scoped to be **as independent as possible** so they can be delegated to different workers in parallel; cross-phase dependencies are stated explicitly at the top of each phase. Each phase decomposes into **vertical build slices** that ship working behaviour end-to-end, in line with `CLAUDE.md` § 11–12.

The goal is bluntly stated: bring the payroll module to the level of the products it was benchmarked against. No half-measures, no opportunistic redesigns of unrelated modules.

---

## 0. Cross-cutting non-negotiables (apply to every phase)

These rules govern every slice in every phase. A slice is not "done" until it satisfies these.

1. **Architecture flow** — UI → Service → Repository → Models. UI never opens sessions, never writes journals, never owns posting rules. Per `CLAUDE.md` § 4.
2. **Accounting truth lives in journal entries**, not in payroll tables. Posting goes through controlled posting services. § 7.
3. **Company scoping is mandatory** on every list/query/mutation. § 6.
4. **Field-level validation**, not form-level. Real-time feedback with inline error placement. Form `_on_accept` is a *last* line of defence, not the only one.
5. **No raw enum codes in UI strings.** Display strings live in i18n-ready label maps with explicit fallbacks logged, not silently shown.
6. **No magic numbers in code.** Defaults (variance threshold, effective dates, severity colours) come from settings, theme tokens, or company configuration.
7. **No modal-on-modal.** Issue resolution is via inline panels or non-blocking side drawers.
8. **All destructive verbs (Void, Delete, Deactivate, Reverse) are double-confirmed.** Reversal of posted runs requires typed confirmation.
9. **Every primary surface is keyboard-first navigable.** Tab order, shortcut map, focus rings, screen-reader labels.
10. **Every primary surface is responsive** — `setMinimumSize` / `setMaximumSize` / layout stretches; no `resize(...)` literals on dialogs/wizards.
11. **Every business event is auditable.** All state transitions emit audit log rows through the audit service, not via UI shortcuts.
12. **Validation runs through one validation engine.** Calculation, posting, payment and remittance reuse the same engine with rule codes; UI subscribes, never re-implements.
13. **Slices ship behind feature flags** until the phase signs off, so staged rollout doesn't break the existing app for active users.

---

## 1. Phase map and dependency graph

```
                         P1 Design System & Form Primitives  ─────────────────────┐
                              │                                                   │
                ┌─────────────┼──────────────┬──────────────┬──────────────┐      │
                ▼             ▼              ▼              ▼              ▼      │
   P2 IA Reset        P3 Run Workbench   P4 Hire-to-Pay   P9 Calc        P11 Terms│
   (Workbench shell)  (single page)      (threaded BP)    Transparency   & Glossary
                │             │              │              │
                └─────────────┴──────┬───────┘              │
                                     ▼                      │
                         P6 Posting/Payments/Remit          │
                         Unification                        │
                                     │                      │
                                     ▼                      │
                         P7 Approvals & SoD                 │
                                     │                      │
                                     ▼                      │
                         P8 Off-cycle / Reverse / YTD       │
                                     │                      │
                                     ▼                      │
                         P5 Component→Authority Map ◄───────┘
                                     │
                                     ▼
                         P10 Statutory Pack Lifecycle
                                     │
                                     ▼
                         P12 Empty States / Help / Onboarding
                                     │
                                     ▼
                         P13 A11y / Keyboard / Responsive
                                     │
                                     ▼
                         P14 Audit / Telemetry / Validation hardening
```

Parallelisability summary:

| Phase | Can start when | Parallel with |
|---|---|---|
| P1 Design System & Form Primitives | Day 1 | nothing else (foundation) |
| P2 IA Reset | After P1 S1 (workspace shell tokens) | P3, P4, P9, P11 |
| P3 Run Workbench | After P1 S1–S3 | P2, P4, P9, P11 |
| P4 Hire-to-Pay BP | After P1 S1–S3 | P2, P3, P9, P11 |
| P5 Component→Authority Map | Service-only slice can start day 1; UI after P6 | P10 |
| P6 Posting/Payments/Remit Unification | After P3 ships preparer flow | P5 service slice |
| P7 Approvals & SoD | After P3 + P6 | P5, P10 |
| P8 Off-cycle / Reverse / YTD | After P7 | P5, P10 |
| P9 Calc Transparency | After P1 | P2, P3, P4 |
| P10 Statutory Pack Lifecycle | After P5 service slice | P6, P7 |
| P11 Terminology / Glossary | Day 1 (audit + spec slice) | every other phase |
| P12 Empty States / Help / Onboarding | After every phase ships first slice | rolling |
| P13 A11y / Keyboard / Responsive | Day 1 (token slice) + after each surface | rolling |
| P14 Audit / Telemetry / Validation hardening | After every state transition is wired | rolling |

Everything south of P6 in the graph is sequential because it depends on the canonical "payroll run as a threaded artifact" being in place.

---

# Phase 1 — Design System & Form Primitives (FOUNDATION)

**Goal.** Eliminate the form-level smell catalogue by building the shared widgets and dialog conventions that every other phase consumes. Without P1 every other phase will silently regress.

**Why first.** Every UX symptom in §6 of the audit (numeric `QLineEdit`, dead date controls, raw enum strings, hex colour soup, modal-on-modal, no confirmations) is a missing or weak primitive. Fix the primitives and ten dialogs improve at once.

**Out of scope.** Module-level IA, business processes, calc engine — those are P2+.

**Dependencies.** None. Owns `src/seeker_accounting/shared/ui/`.

### Slice P1.S1 — Design tokens and theme audit
- Inventory every hex literal in `modules/payroll/ui/`. Produce `payroll_inline_styles_audit.md` (already partially exists for app-wide styles — extend it).
- Land status-chip tokens (`token.status.draft / calculated / approved / posted / voided / paid / partial / error / warning / info`) in `shared/ui/styles/tokens.py`.
- Land severity tokens (`token.severity.blocker / error / warning / info / notice`).
- Add semantic spacing tokens for dialog layouts.
- **Acceptance:** zero hex literals in payroll UI files; `qss_builder` smoke test passes; light + dark snapshots reviewed.

### Slice P1.S2 — Money / quantity / rate widgets
- `MoneyInput` (locale-aware, ISO 4217 currency context, `Decimal`-backed, min/max, optional negative, optional zero, accessible label).
- `RateInput` (percentage 0–100 with stored value as ratio or pct per setting).
- `QuantityInput` (integer or 4-dp decimal).
- `CurrencyPicker` (loads from active company currencies; never accepts free text).
- All four widgets emit `valueChanged(value, is_valid, reason)` for live validation.
- **Acceptance:** widget gallery smoke; replaces no production dialogs yet.

### Slice P1.S3 — Form dialog primitives
- `FormDialog` base extending `BaseDialog`: section grouping, sticky footer, inline error band, save-state ("dirty/clean/saving/saved"), unsaved-changes guard, escape-confirm.
- `ConfirmDialog` standard for destructive verbs (warn → typed-confirm → double-confirm tiers).
- `InlineIssueBand` for top-of-dialog validation.
- `SidePanel` widget for non-modal context (replaces modal-on-modal).
- **Acceptance:** widget gallery + visual regression baselines.

### Slice P1.S4 — Status chips, severity pills, code-to-label registry
- `StatusChip(state, kind)` consuming P1.S1 tokens.
- `SeverityPill(severity)` for validation issues.
- `CodeLabelRegistry`: a single registry that maps every enum value (`component_type_code`, `payroll_run_status`, `severity`, `payroll_remittance_authority`, etc.) to a displayed label and tooltip. Missing keys log warnings instead of leaking the raw code.
- **Acceptance:** lint rule rejects new direct enum-string display in payroll UI; existing leaks tracked by ticket.

### Slice P1.S5 — Form validators & async validation pipeline
- `FieldValidator` protocol + standard implementations (required, decimal range, date range, regex, async lookup, cross-field, currency-in-company, account-in-coa).
- Live validation pipeline: keystroke debounce, error placement under field, live OK/disabled state on primary action.
- **Acceptance:** sample form proves zero-submit-time errors; benchmarked vs. Gusto's "live validate" latency budget.

### Slice P1.S6 — Wizard framework v2
- `WizardShell` with: declarative `Step(id, title, optional, gate)` list, completion state per step (◯ pending, ▷ current, ✓ done, ⚠ has issues, ⤳ skipped), step jump where `gate` allows, persistent draft state (server-checkpointed), keyboard navigation, side-panel for errors, no `resize(...)`.
- All six existing wizards will migrate onto this shell in their respective phases.
- **Acceptance:** reference wizard built and tested; old wizards still on legacy shell behind a flag.

### Slice P1.S7 — Empty-state, hero card, KPI tile primitives
- `EmptyState(headline, body, primary_action, secondary_action, illustration_token)`.
- `KpiTile(label, value, trend, drilldown)`.
- `WorkbenchHeader(title, period_picker, primary_action, breadcrumb)`.
- **Acceptance:** widget gallery; visual regression baselines.

### Slice P1.S8 — Lint + pre-commit guards
- AST lint rule: forbid `QLineEdit` for fields whose name matches `(amount|salary|rate|qty|quantity|net|gross|tax|cnps|pit)` in `modules/payroll/`.
- AST lint rule: forbid raw enum string in UI, forbid `resize(`, forbid hex literals in `modules/payroll/ui/`.
- Pre-commit hook runs the rules.
- **Acceptance:** CI fails on regression; baseline of existing violations recorded as a tracked ledger.

---

# Phase 2 — Information Architecture Reset

**Goal.** Replace the four-sidebar-node, schema-driven IA with a **single Payroll Workbench** organised by user task, mirroring Workday / Gusto / Sage 300 People / SAP EC Payroll.

**Why.** Audit §3.1–§3.3: 4 sidebar nodes × 17 tabs is engineering-driven, not user-driven; the same data appears on multiple surfaces; topbars are inconsistent.

**Dependencies.** P1.S1, P1.S7 (workbench header, KPI, empty states).

**Out of scope.** Run logic, hire logic — they are consumed but not changed by P2; their *home* is changed.

### Slice P2.S1 — Workbench shell
- One sidebar entry: **Payroll**.
- Workbench header: company, pay period picker, KPI tiles (open run, last posted run, employees on payroll, statutory due this month).
- Left rail navigation **inside** the workbench: `Dashboard / Run Payroll / People / Compensation / Setup / Statutory / Reports / Audit`.
- Routing service maps deep-link IDs (`payroll.run`, `payroll.run.detail`, `payroll.people.profile/123`) so any external link still works.
- **Acceptance:** new shell renders behind flag; old four pages still reachable via legacy nav.

### Slice P2.S2 — Dashboard pane
- Pay period card with state badge (Open / Calculating / Calculated / Approved / Posted / Paid / Closed).
- "Next actions" task list (computed: e.g., "3 employees missing CNPS number", "Variance review pending on Jan 2026 run").
- Recent activity feed (audit-driven).
- **Acceptance:** dashboard reads from existing services only — no new data plumbing.

### Slice P2.S3 — People pane (replaces Setup → Employees)
- Master list (search, filters, density toggle, saved views).
- Detail panel on the right: read-only profile, with "Edit", "Hire", "Terminate", "Compensation change" actions.
- Readiness chips (Tax & CNPS, Payment, Compensation, Components).
- **Acceptance:** all employee actions previously reachable from Setup → Employees and Employee Hub Window are reachable here without losing functionality.

### Slice P2.S4 — Compensation pane (replaces Calculation → Profiles + Assignments)
- Two stacked grids: **Profiles** (per employee active/historic) and **Assignments**.
- Effective-dating UI: timeline strip, drill into past/future.
- **Acceptance:** parity with old Calculation tabs 1–2.

### Slice P2.S5 — Setup pane (replaces Setup → Settings/Components/Rules)
- Sectioned settings page with anchor nav: Company / Statutory / Components / Rules / Departments & Positions / Number Format.
- **Acceptance:** parity with `payroll_setup_page` minus the Employees tab.

### Slice P2.S6 — Statutory pane (replaces Operations → Packs + Accounting → Remittances)
- Pack registry, pack diff viewer, applied history, rollover.
- Remittances list (later filled by P5 + P6).
- **Acceptance:** parity with old "Packs" tab.

### Slice P2.S7 — Reports & Audit pane (replaces Operations → Validation/Imports/Print/Audit)
- Reports section: payslips, summary, export.
- Validation section: assessment, issues, drill-through.
- Imports section: department/position/employee.
- Audit section: filterable audit log.
- **Acceptance:** parity; old workspace removed behind flag.

### Slice P2.S8 — Legacy nav retirement
- Remove the four legacy sidebar entries; redirect to workbench.
- Remove ribbon entries that duplicate workbench actions (per audit §3.5).
- **Acceptance:** legacy code paths deleted (not just hidden); regression tests green.

---

# Phase 3 — Run Payroll Workbench (single page, replaces the 7-step wizard)

**Goal.** Replace `payroll_run_wizard.py` with a **single-page run cockpit** modelled on Workday "Run Pay Calculation Results" and Gusto's "Run payroll" page. Wizards remain only for activation, hiring, and compensation change.

**Why.** Audit §2.1, §5.3: a recurring monthly task does not belong in a 7-step wizard.

**Dependencies.** P1.S1–S5, P1.S7. Lives inside P2.S1 workbench but can be developed in parallel against the legacy shell.

### Slice P3.S1 — Run cockpit shell
- Three regions: header (period, currency, status, primary action), centre (employee grid), right rail (issues, variance, audit, posting hand-off).
- Canonical state machine for `PayrollRun`: `draft → inputs_collected → calculated → variance_reviewed → approved → posted → settling → paid → closed` plus `voided`, `reversed`. Every transition through a service method, every transition audited.
- **Acceptance:** can open an existing draft run in the cockpit and see the same data the old wizard exposed.

### Slice P3.S2 — Inputs panel
- Inline variable-input grid (replaces the separate batch dialog being launched mid-wizard).
- Add / edit / approve lines without leaving the cockpit.
- Bulk paste (CSV-on-clipboard) with row-level validation.
- **Acceptance:** create a run, add a one-time bonus inline, calculate, see it reflected.

### Slice P3.S3 — Calculate with dry-run preview
- "Calculate" is gated by a confirm step that shows: number of employees, expected gross, expected net, currency, period — before commit.
- Long calculation runs render a progress UI with cancel.
- Calculation is async-safe; cockpit shows skeleton state.
- **Acceptance:** dry-run-then-commit pattern verified on 100-employee fixture company.

### Slice P3.S4 — Employee grid
- Columns: employee, gross, total earnings, total deductions, statutory, net, variance, status, action menu.
- Right-aligned numeric columns, sortable, sticky header, density toggle.
- Row-level expand: per-line earnings/deductions breakdown.
- Filter chips (variance > X%, status = exception, missing-mapping, excluded).
- **Acceptance:** parity-plus vs. old per-run table.

### Slice P3.S5 — Variance explainability (consumed from P9)
- Right rail "Why did this change?" panel for selected employee: per-component delta vs. prior run, drivers (new component, rate change, input batch, pack rollover), narrative.
- **Acceptance:** matches Workday's audit-report level of detail; threshold is configurable per company.

### Slice P3.S6 — Inclusion / exclusion model
- Row action: include / exclude with structured reason taxonomy (terminated mid-period, on unpaid leave, dispute, off-cycle, other-with-text).
- Excluded rows persist to audit log with reason and actor.
- **Acceptance:** parity with old wizard step 6, but stays in the cockpit.

### Slice P3.S7 — Approval hand-off
- "Submit for approval" button (cockpit primary action when state == `variance_reviewed`).
- Approver sees a read-only cockpit with Approve / Send back actions.
- Lives behind P7 SoD slice; UI shell ships first.
- **Acceptance:** preparer can submit, approver can approve/reject, full audit trail.

### Slice P3.S8 — Retire `payroll_run_wizard.py`
- Migrate any one-time call sites; delete the file and its dialog references.
- **Acceptance:** zero references to the wizard remain; no regression on monthly run smoke.

---

# Phase 4 — Hire-to-Pay Threaded Business Process

**Goal.** Collapse "Setup → Employee form" + "Employee Hub readiness" + "Employee Payroll Setup Wizard" + "Component Assignment Dialog" + "Compensation Profile Dialog" into a **single threaded Hire BP** modelled on Workday's hire process.

**Why.** Audit §5.2: the user is shuffled across 3+ surfaces to make one employee payroll-ready. Validation surfaces late, at run/post time.

**Dependencies.** P1.S1–S6, P11 glossary slice (so we stop saying "Profile" / "Compensation Profile" / "Compensation" interchangeably).

### Slice P4.S1 — Hire BP service & state machine
- `EmployeeOnboarding` aggregate with steps: Identity → Employment → Compensation → Payment Election → Statutory IDs → Components → Review.
- Server-side draft persistence so the user can leave and resume.
- Each step has its own validator using P1.S5 pipeline.
- Required fields are *required* — no late validation: tax ID, CNPS, payment account become structurally required when Hire BP completes (the existing employee-form "optional" semantic is retained only for legacy edits of existing employees).
- **Acceptance:** can start, leave, return, complete; audit log shows full BP.

### Slice P4.S2 — Hire BP UI on wizard framework v2
- Six labelled steps with completion semantics; "Payment" step gets explicit copy ("How will this person be paid?"); jump-to-step where gate allows; review step is editable (click section to jump back).
- **Acceptance:** the empty-step copy issue (audit §2.1, line 78) is gone; review is actionable.

### Slice P4.S3 — Compensation step UX
- Side-by-side current vs. new comparison for compensation changes (reusable component for the change-comp wizard, P4.S5).
- Effective dating timeline.
- **Acceptance:** mirrored with `compensation_change_wizard` after P4.S5.

### Slice P4.S4 — Components step
- Grid view (not the QListWidget checkbox list). Columns: code, name, type, method, default rate/amount, override, status. Inline override using P1.S2 numeric widgets.
- Mandatory components flagged with badge; cannot be unchecked unless eligibility rule allows.
- **Acceptance:** parity-plus vs. old wizard step 5.

### Slice P4.S5 — Compensation Change Wizard migration
- Migrate `compensation_change_wizard.py` onto the new shell using P4.S3 shared widgets.
- **Acceptance:** parity, plus side-by-side view, plus effective-date timeline.

### Slice P4.S6 — Termination and Rehire BPs
- Termination BP: last-pay date, severance, final-pay options, exit checklist.
- Rehire BP: prior employee detection, carry-forward of YTD where applicable.
- **Acceptance:** new BPs available from People pane (P2.S3).

### Slice P4.S7 — Retirement of legacy surfaces
- Remove `employee_payroll_setup_wizard.py`, the readiness-only `employee_hub_window.py` (its content moves into P2.S3 detail panel).
- Keep `employee_form_dialog.py` only for in-place light edits (phone, email) — power flows go through Hire BP / Termination BP / Compensation Change BP.
- **Acceptance:** zero references to the retired wizard; smoke green.

---

# Phase 5 — Component → Authority Mapping & Auto-Remittance Engine

**Goal.** Eliminate the "manual amount entry" smell in the remittance wizard (audit §2.6, §5.3 last row) by introducing a first-class **component-to-authority mapping** and an **auto-seeded remittance engine**.

**Why.** Today the user types CNPS / DGI amounts from memory because the data model lacks a mapping. This is a *correctness* defect, not just UX.

**Dependencies.** None for service slices; UI slices depend on P6.

### Slice P5.S1 — Data model + Alembic migration
- New table `payroll_component_authority_map(company_id, component_id, authority_code, line_kind, side, fraction)`.
- Authority registry `payroll_authority(company_id, code, name, jurisdiction, filing_cadence, deadline_rule, gl_liability_account_id)`.
- Migration is additive only; no data loss.
- **Acceptance:** Alembic up + down clean.

### Slice P5.S2 — Auto-seed from statutory packs
- Statutory packs declare default authority mappings. Pack apply seeds the map.
- User can override per company.
- **Acceptance:** apply Cameroon pack → CNPS, DGI, FNE, CFC mappings present.

### Slice P5.S3 — Remittance engine service
- Given (authority, period, run scope), compute the remittance lines from posted run results using the map. No manual amount entry.
- Recompute / preview / commit semantics.
- **Acceptance:** golden-fixture totals match expected.

### Slice P5.S4 — Remittance UI redesign
- Single-page remittance editor (no wizard): authority + period picker → lines auto-populated → review variance vs. expected → optional override with reason → commit.
- Filing deadline banner at the top.
- **Acceptance:** retire `remittance_wizard.py`; smoke green.

### Slice P5.S5 — Statutory return pre-fill
- Returns (DSF year-end, CNPS quarterly, DGI monthly) read directly from the engine; no separate data entry.
- Cross-link from each return box to the contributing run lines.
- **Acceptance:** auditor-traceable from a return box back to a journal line.

---

# Phase 6 — Posting / Payments / Remittances Unification

**Goal.** Replace the three-tab "Accounting workspace" with **one threaded artifact**: the payroll run flows from calculate → approve → post → settle → pay → remit on a single timeline.

**Why.** Audit §5.3, §3.3: the same data surfaces on four different tabs and the user re-enters values to integrate the chain.

**Dependencies.** P3 cockpit, P5 service slice, P1.S3 SidePanel.

### Slice P6.S1 — Run timeline component
- Horizontal timeline at the top of the cockpit: Draft → Calculated → Approved → Posted → Paid → Closed, with side-branches Voided / Reversed / Off-cycle.
- Each node clickable; opens the relevant pane in the right rail.
- **Acceptance:** every transition observable from one place.

### Slice P6.S2 — Inline post-to-GL
- Posting moves into the cockpit as a right-rail action with inline validation panel (no modal-on-modal).
- Quick-fix actions open `SidePanel`s scoped to the issue (account role mapping, period unlock, missing component account).
- Posting writes through controlled posting service (CLAUDE.md §7).
- **Acceptance:** retire `payroll_post_run_dialog.py`; modal-on-modal eliminated.

### Slice P6.S3 — Settlement & payments
- Per-employee payment grid in the cockpit; mark paid / partial / hold; bulk actions.
- Bank-file generation (CSV / SEPA equivalent) where applicable.
- **Acceptance:** retire payment-record dialog as the primary entry; keep it only as a fallback for one-off adjustments.

### Slice P6.S4 — Remittance hand-off from cockpit
- Cockpit "Remit" panel lists authorities owed for this run with computed amounts (from P5).
- One click moves into the remittance editor (P5.S4) pre-scoped to the right authority and period.
- **Acceptance:** the user never manually re-enters amounts.

---

# Phase 7 — Approvals & Segregation of Duties

**Goal.** Add a real preparer/approver split so a single user cannot Calculate → Approve → Post → Pay alone.

**Why.** Audit §5.4. ISA 315 / SOX-equivalent expectation.

**Dependencies.** P3, P6.

### Slice P7.S1 — Role and permission model
- Roles: `payroll_preparer`, `payroll_approver`, `payroll_poster`, `payroll_payer`, `payroll_admin`.
- Permission checks on every state transition service method.
- **Acceptance:** RBAC unit tests cover each transition.

### Slice P7.S2 — Approval routing
- Configurable approvers per company, optional multi-approver chain, optional threshold-based routing (e.g., runs > X XAF require CFO).
- **Acceptance:** approval chain visible in the cockpit timeline.

### Slice P7.S3 — Send-back / rework cycle
- Approver can send back with structured reason; cockpit re-opens to preparer in `calculated` state with annotations.
- **Acceptance:** full round-trip auditable.

### Slice P7.S4 — Four-eye for posting and payment
- Posting requires approver role separate from preparer.
- Payment marking can require a third role (configurable).
- **Acceptance:** test that the same user cannot complete the full chain when SoD is enforced.

---

# Phase 8 — Off-cycle, Reversal & YTD Correction

**Goal.** Add the missing payroll lifecycle flows: off-cycle bonus run, reversal of a posted run, YTD correction for closed periods.

**Why.** Audit §5.5. Mid-market peers all ship this.

**Dependencies.** P3, P6, P7.

### Slice P8.S1 — Off-cycle run
- New "Off-cycle" run type, scoped to selected employees, with reason taxonomy (bonus, missed pay, correction).
- Same cockpit, distinct status badge, distinct journal narration.
- **Acceptance:** off-cycle run posts independently.

### Slice P8.S2 — Reversal
- Reversing a posted run produces a counter-journal, marks the original as `reversed`, requires typed confirmation and an approver of equal-or-higher rank.
- Reversal is never a delete; original truth preserved.
- **Acceptance:** GL net effect is zero; audit trail shows full chain.

### Slice P8.S3 — YTD correction
- "Correct prior period" flow: pick employee, pick period, apply delta. Engine computes YTD effect; statutory return effect; payslip note.
- **Acceptance:** corrected YTDs reflected in subsequent runs and statutory returns.

---

# Phase 9 — Calculate Transparency & Variance Explainability

**Goal.** Replace the opaque ±10% acknowledgement with a Workday-grade audit experience.

**Why.** Audit §2.5, §6 #19.

**Dependencies.** P1.S1, P3.S5 consumes this.

### Slice P9.S1 — Calc engine instrumentation
- Engine emits, per employee per component, a `CalcStep(input_basis, formula_id, inputs, output, source_ref)` trace.
- Stored compact and indexed by run + employee.
- **Acceptance:** trace replay reproduces output exactly.

### Slice P9.S2 — Variance driver computation
- Service computes per-employee delta vs. prior run, decomposed by component, classified into drivers (rate change, basis change, new component, removed component, input batch, pack rollover).
- **Acceptance:** golden-fixture verifies driver classification.

### Slice P9.S3 — UI: per-employee explainer
- Right-rail panel in cockpit with narrative explanation, driver chips, component-level table.
- **Acceptance:** non-technical user can answer "why is Joe's net up 14%?".

### Slice P9.S4 — Configurable thresholds
- Variance threshold per company, per component class.
- Replaces hardcoded ±10%.
- **Acceptance:** company-level setting respected end-to-end.

### Slice P9.S5 — Pre-commit dry-run report
- Exportable (PDF/Excel) "Calculation audit pack" before approval (Sage Paie "État de Préparation" parity).
- **Acceptance:** export validated against fixture run.

---

# Phase 10 — Statutory Pack Lifecycle

**Goal.** Make statutory packs a proper first-class lifecycle (registry, diff, rollover, deprecation) rather than a free-text version field.

**Why.** Audit §4.10 (component dialog), §6 #15 (free-text pack version).

**Dependencies.** P5.S1.

### Slice P10.S1 — Pack registry as data
- Move pack manifests into a structured registry; CompanyPayrollSettings references pack by FK, not free text.
- **Acceptance:** invalid pack codes rejected at the form layer.

### Slice P10.S2 — Pack diff viewer
- For a selected pack, show component / rule / authority deltas vs. currently applied pack.
- **Acceptance:** diff renders for Cameroon pack v1 → v2 fixture.

### Slice P10.S3 — Rollover BP
- Wizard (legitimate use of a wizard: rare, high-stakes): preview impact → schedule effective date → apply → audit.
- **Acceptance:** rollover dry-run + commit smoke.

### Slice P10.S4 — Deprecation & guardrails
- Deprecated packs can't be applied; runs already on a deprecated pack get a banner; year-end migration recommended.
- **Acceptance:** deprecation enforced and visible.

---

# Phase 11 — Terminology & Glossary Enforcement

**Goal.** Stamp out the "Run vs. Payroll Run", "Component vs. Payroll Component", "Variable Input vs. Input Batch", "Compensation Profile vs. Profile" inconsistencies.

**Why.** Audit §6 #7. Cheap to fix, expensive to leave.

**Dependencies.** None.

### Slice P11.S1 — Glossary spec
- Canonical term sheet in `docs/payroll_glossary.md`. One canonical name per concept, plus rejected synonyms.
- **Acceptance:** signed off by product owner.

### Slice P11.S2 — String audit
- Sweep every UI string in `modules/payroll/ui/`; replace with canonical terms.
- **Acceptance:** automated scan finds zero rejected synonyms.

### Slice P11.S3 — Lint guard
- Pre-commit rule rejects rejected synonyms in `modules/payroll/`.
- **Acceptance:** CI catches a deliberately introduced synonym.

### Slice P11.S4 — i18n scaffolding
- All payroll UI strings wrapped in `tr(...)`; English baseline; French ready (Cameroon target market).
- **Acceptance:** language switch swaps payroll strings.

---

# Phase 12 — Empty States, Help, Onboarding & Inline Guidance

**Goal.** Replace the generic "No items yet" empty states and ad-hoc help with intentional onboarding and contextual coaching.

**Why.** Audit §6 #11; help articles exist (Phase 1 work) but are not surfaced inline at the right moment.

**Dependencies.** P1.S7; rolling per surface.

### Slice P12.S1 — Empty-state library
- Per surface: headline + one-liner + 1 primary action + 0–1 secondary action + linked help article.
- **Acceptance:** every payroll empty state uses the library; zero generic strings.

### Slice P12.S2 — First-run checklist
- Workbench dashboard shows a setup checklist (configure settings → apply pack → add departments → add positions → add first employee → run first payroll).
- Each item dismissable; persistent until first complete payroll posts.
- **Acceptance:** new-company smoke shows the full checklist.

### Slice P12.S3 — Inline coach marks
- Tooltip + "Learn more" links on first encounter of unfamiliar terms (CNPS Regime, Risk Class, Pack, BIK Mode).
- **Acceptance:** dismissable, never re-shown after dismissal.

### Slice P12.S4 — Help-content audit & top-up
- Re-audit `HELP_CONTENT` keys against the new IA; fill gaps; refresh stale articles.
- **Acceptance:** every workbench surface has a help_key that resolves.

---

# Phase 13 — Accessibility, Keyboard, Responsive Layout

**Goal.** Bring the module to the keyboard-first / screen-reader-aware / responsive standard the audit said it lacks.

**Why.** Audit §6 #9, #10, #14. Dignity of product.

**Dependencies.** P1; rolling per surface.

### Slice P13.S1 — Tokenised sizing
- Replace every `resize(...)` literal with min/max/preferred constraints from spacing tokens.
- **Acceptance:** lint guard from P1.S8 stays green.

### Slice P13.S2 — Keyboard nav per surface
- Tab order audited per workbench pane.
- Shortcuts: Ctrl+N new, Ctrl+E edit, Del delete-with-confirm, Ctrl+Enter submit, Ctrl+Shift+P run payroll, Ctrl+Shift+E new employee, etc.
- **Acceptance:** keyboard-only walk-through completes a full hire-to-pay cycle.

### Slice P13.S3 — Focus rings, accessible names, screen-reader labels
- Every interactive widget has an accessible name; focus rings consistent; tables expose column headers.
- **Acceptance:** automated a11y check passes.

### Slice P13.S4 — Density modes
- Comfortable / compact density toggle on every grid; persisted per user.
- **Acceptance:** Compact mode reduces row height by ≥25% with no truncation.

---

# Phase 14 — Audit, Telemetry & Validation Hardening

**Goal.** Make every state transition observable, every validation result diagnosable, every UX hypothesis measurable.

**Dependencies.** Rolling.

### Slice P14.S1 — Unified validation engine
- One engine consumed by Hire BP, Run cockpit, Posting, Payments, Remittance, Returns. Rule codes are stable, documented, and surfaced via `CodeLabelRegistry` (P1.S4).
- **Acceptance:** zero duplicate validation logic across services.

### Slice P14.S2 — Audit log breadth
- Every state transition, every override, every reason taxonomy choice, every BP step audited with actor / before / after / reason.
- **Acceptance:** posted-run audit pack reproduces full lineage.

### Slice P14.S3 — Telemetry (opt-in)
- Anonymous funnel metrics: time-to-first-payroll, abandonment per BP step, validation issue frequency.
- **Acceptance:** dashboard shows funnel for fixture company.

### Slice P14.S4 — Smoke + fixture matrix
- A fixture company driven through: setup → 5 employees hired → monthly run × 3 → off-cycle → reversal → year-end DSF. Reproducible end-to-end smoke.
- **Acceptance:** CI runs the matrix.

---

## 2. Delegation guide

Suggested squad split (each squad can take one or more phases independently):

| Squad | Phases | Notes |
|---|---|---|
| **Foundation squad** | P1, P11, P13 | Ships primitives, glossary, a11y; unblocks everyone. |
| **IA squad** | P2, P12 | Workbench shell + onboarding. Depends on foundation S1–S3. |
| **Run squad** | P3, P9 | Cockpit + transparency. Largest user-visible win. |
| **People squad** | P4 | Hire-to-pay BPs. |
| **Money-flow squad** | P5, P6, P7, P8 | Component map, posting/payments/remit unification, SoD, off-cycle. The heaviest sequential chain; needs senior ownership. |
| **Statutory squad** | P10 | Pack lifecycle. |
| **Quality squad** | P14 | Audit, telemetry, fixture matrix. Ongoing. |

## 3. Sign-off gates

A phase is **done** only when:

1. Every slice's acceptance is met.
2. All cross-cutting non-negotiables (§0) hold inside the phase's surfaces.
3. Lint guards (P1.S8) green for the affected files.
4. Smoke + fixture matrix (P14.S4) green including the new behaviour.
5. Help articles for the new surfaces exist and resolve (P12.S4).
6. Glossary lint (P11.S3) green.
7. Visual regression baselines refreshed and reviewed.
8. Feature flag flipped on for staging; opt-in beta company runs a full month.
9. Old surfaces / wizards / dialogs the phase replaces are *deleted*, not just hidden.

## 4. Anti-goals

To stay disciplined, this program will **not**:

- Redesign other modules opportunistically (CLAUDE.md §11, §22).
- Reintroduce wizards for recurring tasks.
- Hide business logic in dialogs (§17).
- Introduce per-page bespoke styling instead of consuming the design system.
- Treat operational documents as accounting truth (§7).
- Add denormalised running balances or YTD shortcut fields.

## 5. Glossary stub (will move to its own doc in P11.S1)

- **Run** — a single payroll cycle for a company, period, currency, type (regular / off-cycle / correction). Canonical UI label: **Payroll run**.
- **Component** — a defined earning, deduction, tax, employer-contribution, or memo line. Canonical: **Payroll component**.
- **Compensation** — the structured pay package for an employee at a point in time. Canonical: **Compensation** (no "profile" suffix in UI).
- **Assignment** — the linkage of a component to an employee with override and effective dates. Canonical: **Component assignment**.
- **Variable input** — period-specific input (overtime hours, one-time bonus, deduction). Canonical: **Variable input**. The container is **Input batch** *only* in the persistence model — the UI shows individual inputs.
- **Statutory pack** — a versioned manifest of components, rules, and authority mappings for a jurisdiction. Canonical: **Statutory pack**.
- **Authority** — a recipient of statutory remittances (CNPS, DGI, FNE, CFC). Canonical: **Statutory authority**.
- **Remittance** — an outbound statutory payment / declaration for an authority and period.
- **Hire / Termination / Compensation Change / Off-cycle / Reversal / YTD Correction** — named business processes. Capitalised in headings.

