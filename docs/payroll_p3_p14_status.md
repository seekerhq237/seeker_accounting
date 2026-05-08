# Payroll UX Remediation Plan — P3-P14 Status Ledger

_Audit + targeted implementation pass, single session._

This ledger summarises the actual state of the Payroll UX Remediation Plan
(`docs/payroll_ux_remediation_plan.md`) against the codebase, what was
implemented in this session, and what remains.

The headline finding from the audit subagent is that **the payroll module is
substantially further along than the plan document suggests** — most of P3-P11
ships in code today. The remaining gaps were small, well-bounded slices.

---

## Session changes

### 1. P14.S3 — Telemetry funnel instrumentation
**Status:** wired through the full monthly_run funnel.

- `payroll_run_service.py`: added `record_funnel_step` calls in
  `submit_run_for_review`, `send_back_run`, `approve_run`, `void_run`
  (run_submitted / run_sent_back / run_approved / run_voided). The pre-existing
  `run_created` and `run_calculated` events remain.
- `payroll_posting_service.py`: added optional `telemetry_service`
  constructor argument and emits `run_posted` and `run_reversed` events after
  successful commit.
- `factories.py`: `create_payroll_run_service` and
  `create_payroll_posting_service` now inject the default
  `TelemetryService` so the funnel actually fires in production. (Previously
  the service code was wired but the factories never passed the dependency,
  making the telemetry calls dead.)
- All eight stages of the documented `monthly_run` funnel are now emitted.

### 2. P13.S2 — Global payroll keyboard shortcuts
**Status:** workbench-page globals now installed (pane-local shortcuts already
existed for run / people / compensation panes).

- `payroll_workbench_page.py`:
  - Imports `install_shortcut`, `shortcut_map`.
  - On construction, installs `Ctrl+Shift+P` → `_trigger_global_new_run` and
    `Ctrl+Shift+E` → `_trigger_global_hire_employee`.
  - These switch to the appropriate pane (run / people) and invoke the
    pane's primary create action.

### 3. Cleanup — `EmbeddedWorkspacePane`
- Deleted
  `src/seeker_accounting/modules/payroll/ui/workbench/panes/embedded_workspace_pane.py`.
- The file was dead code (zero references repo-wide) but its docstring
  advertised itself as a temporary Phase-2 deferral, which falsely suggested
  the workbench was incomplete. Native panes (`people_pane`,
  `compensation_pane`, `setup_pane`, `statutory_pane`, `run_pane`,
  `dashboard_pane`, `reports_pane`, `legacy_link_pane`) replaced it.

### 4. Earlier in the session — Reporting Insights tab
- Removed the duplicate "Insights" tab from
  `reporting_workspace_service.py` (it cloned the Analytics tile list).
- Updated `tests/test_slice_14h_financial_analysis.py` accordingly.

---

## Validation

- `pytest -k payroll` → **390 passed, 2 skipped, 8 subtests passed.**
- `pytest -k "payroll_run or payroll_posting or payroll_workbench"` →
  **46 passed, 2 skipped.**
- `scripts/check_payroll_terminology.py` → clean.
- `scripts/payroll_lint_ast.py` → 25 pre-existing hex-colour violations in
  files **not** touched by this session
  (`payroll_run_posting_detail_dialog.py`, `remittance_editor_dialog.py`,
  `validation_check_detail_dialog.py`, `payroll_accounting_workspace.py`,
  `payroll_operations_workspace.py`, `payroll_run_cockpit.py`,
  `payroll_run_timeline.py`). These belong to a separate styling-cleanup
  slice; per CLAUDE.md §21 they are not bundled into this change.

---

## Phase-by-phase status snapshot (post-session)

Source of truth: cross-referenced subagent audit + this session's edits.

| Phase | Status | Notes |
|------:|:-------|:------|
| P1 | Complete | Foundations — wizard shell, ribbon, status chips, toolkit. |
| P2 | Complete (effectively) | All four legacy workspaces now have native workbench panes. `EmbeddedWorkspacePane` deleted. |
| P3 | Complete | Hire-employee BP wizard exists. |
| P4 | Complete | Onboarding drafts persisted; resume flow live. |
| P5 | Complete | Component / formula / ruleset workflows in setup pane. |
| P6 | Complete | Compensation pane + scheduled changes. |
| P7 | Complete | Run cockpit, timeline, validation drilldown. |
| P8 | Complete | Posting service + payslip preview + posting detail dialog. |
| P9 | Complete | Remittance editor dialog + statutory pane. |
| P10 | Mostly complete | Authority engine, statutory pack seed, return prefill all green. **Gap remaining:** rollover wizard UI (P10.S3) — service exists (`PayrollPackVersionService.preview_rollover` / `execute_rollover`), only the inline buttons in `payroll_operations_workspace.py` are present. A `WizardShell`-based wrapper is the next step. |
| P11 | Complete | Workforce / employee profile hub. |
| P12 | Mostly complete | Setup checklist widget exists. **Gap remaining:** completeness audit of `help_key` coverage on every checklist step against `help_content.py`. |
| P13 | Complete after this session | Pane-local shortcuts already wired for run/people/compensation. Global Ctrl+Shift+P / Ctrl+Shift+E added in this session. **Optional follow-up:** local shortcuts for `setup_pane` / `statutory_pane` sub-tabs (low value — these tabs have explicit primary buttons; deferred deliberately). |
| P14 | Complete after this session | Telemetry service + opt-in flow + privacy filter were already in place. Full `monthly_run` funnel wired in this session. **Optional follow-up:** funnel events for `employee_onboarding` (already partial), `remittance`, and `correction` flows. |

---

## Remaining work (ranked, with sizing)

1. **P10.S3 — Pack rollover wizard UI (M).** Build a `WizardShell` wrapper
   over `PayrollPackVersionService` (preview → diff review → confirm →
   execute). Existing inline buttons in `payroll_operations_workspace.py`
   stay as a fallback during rollout.

2. **Hex-colour palette migration (M).** Replace 25 raw `#xxxxxx` literals
   in payroll dialogs/workspaces with palette / tokens references. Pure
   styling refactor; lint guard already in place.

3. **P12.S4 — Help-article coverage audit (S).** Walk every `SetupChecklist`
   step and confirm `help_key` resolves in `help_content.py`. Add missing
   entries.

4. **P13.S2 follow-up — Setup / statutory tab shortcuts (XS).** Optional —
   add `Ctrl+N` / `Ctrl+E` to each tabbed sub-pane in `setup_pane.py` and
   `statutory_pane.py`. Each sub-pane has its own `__init__`; the install
   pattern from `people_pane` applies.

5. **P14.S3 follow-up — Funnel events for remittance & corrections (S).**
   Add `record_funnel_step` calls to `payroll_remittance_service.py`
   (batch_created / batch_opened / payment_recorded / batch_reconciled) and
   `payroll_correction_service.py` (correction_applied / correction_voided).

6. **EmployeeOnboardingService factory wiring (S).** The service is
   instantiated nowhere in `factories.py`; the wizard looks it up via
   `getattr(service_registry, "employee_onboarding_service", None)` with a
   `None` fallback. If the wizard is ever exercised in production, this needs
   a `create_employee_onboarding_service` factory and a registry slot.

---

## Files changed this session

- `src/seeker_accounting/app/dependency/factories.py`
- `src/seeker_accounting/modules/payroll/services/payroll_run_service.py`
- `src/seeker_accounting/modules/payroll/services/payroll_posting_service.py`
- `src/seeker_accounting/modules/payroll/ui/workbench/payroll_workbench_page.py`
- `src/seeker_accounting/modules/payroll/ui/workbench/panes/embedded_workspace_pane.py` _(deleted)_
- `src/seeker_accounting/modules/reporting/services/reporting_workspace_service.py` _(earlier in session)_
- `tests/test_slice_14h_financial_analysis.py` _(earlier in session)_
- `docs/payroll_p3_p14_status.md` _(this file)_
