# Payroll Ribbon, Wizard, and Child Window Blueprint

## Purpose

Turn payroll from "four dense tabbed workspaces with many local dialogs" into a clearer shell-level workflow:

- the ribbon should expose the right payroll action for the current sub-workflow
- wizards should own cross-step payroll orchestration
- child windows should own dense, focused work sessions
- short forms should stay short forms

This document is a follow-on to [docs/Wizards.md](./Wizards.md) and [docs/specs docs/ribbon_context_plan.md](./specs%20docs/ribbon_context_plan.md). It narrows those broad plans into a payroll-specific design that matches the code already in place.

---

## Evaluation Of The Current Docs

### What the wizard doc gets right

[docs/Wizards.md](./Wizards.md) is directionally correct about payroll:

- payroll deserves real orchestration wizards, not just more dialogs
- payroll run and year-end flows need preview, validation, and resumability
- employee lifecycle changes are wizard-worthy because they touch setup, calculation, and compliance

### Where the wizard doc is still too abstract

The current payroll section in `Wizards.md` names the right themes, but it does not yet reflect the actual payroll architecture in the app:

- payroll is already split into `payroll_setup`, `payroll_calculation`, `payroll_accounting`, and `payroll_operations`
- several payroll tasks already have focused dialogs and review windows
- payroll permissions are split by setup, input, run, posting, payment, remittance, print, and audit

So the missing piece is not "should payroll have wizards?" It is "which payroll tasks should be wizard-led, and which should stay focused child windows?"

### What the ribbon doc gets right

[docs/specs docs/ribbon_context_plan.md](./specs%20docs/ribbon_context_plan.md) was right to reject a naive "union ribbon" for payroll. A single flat surface with every payroll button would be noisy and unstable.

### Where the ribbon doc is now too conservative

The current Phase 5 recommendation in `ribbon_context_plan.md` is effectively "no ribbon for payroll." That made sense for a first pass, but it leaves a gap:

- payroll has some of the most important guided workflows in the system
- payroll already has shell-level navigation and child-window support
- payroll needs high-value shell entry points more than most modules because the workflows cross tabs and roles

The answer is not "no ribbon." The answer is "payroll needs a smarter ribbon model than list registers do."

---

## Current Payroll Shape In Code

Payroll already behaves like a mini-application inside Seeker:

- [payroll_setup_page.py](./../src/seeker_accounting/modules/payroll/ui/payroll_setup_page.py)
  - tabs: company settings, employees, components, rules
- [payroll_calculation_workspace.py](./../src/seeker_accounting/modules/payroll/ui/payroll_calculation_workspace.py)
  - tabs: compensation profiles, recurring components, variable inputs, payroll runs
- [payroll_accounting_workspace.py](./../src/seeker_accounting/modules/payroll/ui/payroll_accounting_workspace.py)
  - tabs: posting, employee payments, remittances, summary
- [payroll_operations_workspace.py](./../src/seeker_accounting/modules/payroll/ui/payroll_operations_workspace.py)
  - tabs: validation, statutory packs, imports, print, audit log

It also already has several dialogs that are more than simple forms:

- `PayrollInputBatchDialog`
- `PayrollRunEmployeeDetailDialog`
- `PayrollPostRunDialog`
- `PayrollRunPostingDetailDialog`
- `PayrollSummaryDialog`
- `ValidationCheckDetailDialog`

That means payroll needs a three-layer interaction model:

1. ribbon for shell-level workflow entry and context actions
2. wizards for cross-step orchestration
3. child windows for deep single-object work sessions

---

## Core Design Decision

### Recommended payroll ribbon model: hybrid tab-aware surfaces

Do not use:

- one giant workspace ribbon
- no payroll ribbon at all

Use:

- one ribbon surface per active payroll tab or sub-context
- a stable action spine inside each workspace
- only the high-value tab actions in ribbon
- inline filters and local field controls stay inside the page

This is effectively a refined version of "Option A" from the ribbon plan, but with explicit guardrails so the ribbon does not become chaotic.

### Payroll ribbon rules

Every payroll ribbon surface should have only four kinds of actions:

1. One primary workflow action
2. Two to four tab-local actions
3. One review or refresh utility action
4. Two or three related-page shortcuts

Every payroll ribbon surface should avoid:

- mirroring every inline widget from the tab
- showing filters, combo boxes, or period selectors in the ribbon
- showing actions from other tabs unless they are true cross-workflow anchors

---

## Infrastructure Changes Needed

The current ribbon system keys surfaces by `nav_id` or child-window key. Payroll needs one more layer of context.

### Proposed addition

Tabbed payroll workspaces should expose an active ribbon surface key, for example:

- `payroll_setup.settings`
- `payroll_setup.employees`
- `payroll_setup.components`
- `payroll_setup.rules`
- `payroll_calculation.profiles`
- `payroll_calculation.assignments`
- `payroll_calculation.inputs`
- `payroll_calculation.runs`
- `payroll_accounting.posting`
- `payroll_accounting.payments`
- `payroll_accounting.remittances`
- `payroll_accounting.summary`
- `payroll_operations.validation`
- `payroll_operations.packs`
- `payroll_operations.imports`
- `payroll_operations.print`
- `payroll_operations.audit`

### Shell contract

Add one of these patterns:

- `current_ribbon_surface_key()` on the active page
- or a workspace signal that tells the shell to swap the current ribbon surface when the tab changes

### Refresh triggers

Payroll pages should request ribbon state refresh on:

- active tab change
- active company change
- table selection change
- run status change
- dialog accept or mutation complete

---

## What "Context-Aware" Should Mean In Payroll

If all ribbons are supposed to be context-aware, payroll should not stop at tab awareness.

Payroll has at least six context layers:

1. **Location context**
   - payroll setup vs calculation vs accounting vs operations
   - active tab inside that workspace
2. **Object context**
   - no selection
   - employee selected
   - run selected
   - run employee selected
   - remittance batch selected
   - validation issue selected
3. **Lifecycle context**
   - draft
   - calculated
   - approved
   - posted
   - voided
   - active vs inactive employee or rule
4. **Readiness context**
   - setup incomplete
   - validation blockers present
   - warnings only
   - ready for next step
5. **Permission context**
   - the user may be allowed to calculate but not approve
   - may approve but not post
   - may view audit but not manage payroll setup
6. **Session context**
   - main workspace mode
   - child-window deep work mode
   - wizard mode

The payroll ribbon should react to all six, but not in the same way.

### Recommended adaptation rules

- **Location** should switch the ribbon family.
- **Object plus lifecycle** should switch the active micro-surface.
- **Readiness** should influence the primary call to action.
- **Permissions** should disable or remove actions depending on the security posture you want.
- **Session** should let child windows fully take over the ribbon.

### Stability rule

Context awareness should not mean visual chaos.

Use this guardrail:

- the ribbon may change when the user changes tab, selection focus, or workflow state
- the ribbon should not constantly reshuffle for tiny field-level changes
- keep group positions stable even when the specific buttons inside a group change

In practice:

- **left group** = create or begin
- **middle group** = state transition or review
- **right group** = utility and related navigation

---

## Surface Families And Micro-Surfaces

Do not think of payroll as having one surface per tab.

Think of it as:

- one **surface family** per tab
- several **micro-surfaces** inside that family depending on selection and state

Examples:

- `payroll_calculation.runs.none`
- `payroll_calculation.runs.draft_run`
- `payroll_calculation.runs.calculated_run`
- `payroll_calculation.runs.approved_run`
- `payroll_calculation.runs.employee_focus`

- `payroll_accounting.posting.none`
- `payroll_accounting.posting.postable_run`
- `payroll_accounting.posting.posted_run`

- `payroll_setup.employees.none`
- `payroll_setup.employees.active_employee`
- `payroll_setup.employees.inactive_employee`

- `payroll_operations.validation.none`
- `payroll_operations.validation.blocker_selected`
- `payroll_operations.validation.warning_selected`

This is the deeper form of context awareness payroll actually needs.

### Why micro-surfaces are better than only enablement flags

The current ribbon engine can already disable commands, but payroll needs more than disablement:

- when no run is selected, `Approve`, `Void`, and `Employee Detail` are not just disabled; they are not the right conversation
- when an employee result row is selected, the ribbon should pivot from run-level actions to employee-level review actions
- when a posted run is selected, the dominant next step is no longer calculate or approve; it is review posting, payments, remittances, and printing

That means payroll should often **swap the visible surface**, not merely gray out half the bar.

---

## Payroll Context Matrix

### 1. Payroll Setup -> Employees

#### `payroll_setup.employees.none`

Use when no employee row is selected.

Primary:

- `Hire Employee`

Secondary:

- `Employee Hire Wizard`
- `Manage Departments`
- `Manage Positions`
- `Refresh`

#### `payroll_setup.employees.active_employee`

Use when an active employee is selected.

Primary:

- `Compensation Change`

Secondary:

- `Edit Employee`
- `Open Compensation`
- `Open Assignments`
- `Offboard Employee`
- `Refresh`

#### `payroll_setup.employees.inactive_employee`

Use when an inactive employee is selected.

Primary:

- `View Employee`

Secondary:

- `Rehire or Reactivate`
- `Open History`
- `Refresh`

### 2. Payroll Calculation -> Payroll Runs

#### `payroll_calculation.runs.none`

Use when no run is selected.

Primary:

- `Payroll Run Wizard`

Secondary:

- `New Run`
- `Open Validation`
- `Refresh`

#### `payroll_calculation.runs.draft_run`

Use when a draft run is selected.

Primary:

- `Calculate Run`

Secondary:

- `Open Run Workbench`
- `Void Run`
- `Open Variable Inputs`
- `Refresh`

#### `payroll_calculation.runs.calculated_run`

Use when a calculated run is selected.

Primary:

- `Approve Run`

Secondary:

- `Recalculate`
- `Variance Review`
- `Employee Results`
- `Void Run`
- `Refresh`

#### `payroll_calculation.runs.approved_run`

Use when an approved run is selected.

Primary:

- `Open Posting Workbench`

Secondary:

- `Employee Results`
- `Open Summary`
- `Print Payslips`
- `Refresh`

#### `payroll_calculation.runs.employee_focus`

Use when the employee results grid is focused and a run employee row is selected.

Primary:

- `Employee Payroll Detail`

Secondary:

- `Project Allocations`
- `Payslip Preview`
- `Next Employee`
- `Previous Employee`
- `Back To Run`

### 3. Payroll Accounting -> Posting

#### `payroll_accounting.posting.none`

Primary:

- `Posting Workbench`

Secondary:

- `Refresh`
- `Open Validation`

#### `payroll_accounting.posting.postable_run`

Use when an approved or calculated run is selected and can be posted.

Primary:

- `Post To GL`

Secondary:

- `Posting Validation`
- `Open Role Mappings`
- `Open Fiscal Periods`
- `Refresh`

#### `payroll_accounting.posting.posted_run`

Use when a posted run is selected.

Primary:

- `Posting Detail`

Secondary:

- `Open Journal`
- `Open Payments`
- `Open Remittances`
- `Open Summary`
- `Refresh`

### 4. Payroll Accounting -> Remittances

#### `payroll_accounting.remittances.none`

Primary:

- `Remittance Wizard`

Secondary:

- `New Batch`
- `Refresh`

#### `payroll_accounting.remittances.batch_selected`

Primary:

- `Open Batch`

Secondary:

- `Add Line`
- `Record Payment`
- `Cancel Batch`
- `Open Deadline View`
- `Refresh`

### 5. Payroll Operations -> Validation

#### `payroll_operations.validation.none`

Primary:

- `Readiness Wizard`

Secondary:

- `Run Assessment`
- `Refresh`

#### `payroll_operations.validation.blocker_selected`

Primary:

- `Resolve Blocker`

Secondary:

- `Open Detail`
- `Open Payroll Setup`
- `Open Statutory Packs`
- `Open Calculation`
- `Refresh`

#### `payroll_operations.validation.warning_selected`

Primary:

- `Review Warning`

Secondary:

- `Open Detail`
- `Mark For Follow-Up`
- `Refresh`

---

## Recommended Ribbon Surfaces

## 1. Payroll Setup

| Surface key | Primary action | Secondary actions | Related |
| --- | --- | --- | --- |
| `payroll_setup.settings` | `payroll_setup.activation_wizard` | `configure_settings`, `apply_pack`, `open_validation`, `refresh` | `payroll_operations`, `chart_of_accounts`, `payroll_calculation` |
| `payroll_setup.employees` | `payroll_setup.hire_employee_wizard` | `edit_employee`, `compensation_change_wizard`, `offboard_employee_wizard`, `manage_departments`, `manage_positions` | `payroll_calculation`, `payroll_operations` |
| `payroll_setup.components` | `payroll_setup.new_component` | `edit_component`, `deactivate_component`, `apply_pack`, `open_validation` | `chart_of_accounts`, `payroll_operations` |
| `payroll_setup.rules` | `payroll_setup.new_rule_set` | `edit_rule_set`, `edit_brackets`, `deactivate_rule_set`, `apply_pack`, `open_validation` | `payroll_operations`, `payroll_calculation` |

Notes:

- `Activation Wizard` should be the primary shell entry into payroll for a new company.
- Employees need lifecycle actions, not just CRUD.
- Components and rules should keep direct expert actions because payroll admins often need focused maintenance there.
- The employees surface should really be implemented as a family with `none`, `active_employee`, and `inactive_employee` variants.

## 2. Payroll Calculation

| Surface key | Primary action | Secondary actions | Related |
| --- | --- | --- | --- |
| `payroll_calculation.profiles` | `payroll_calculation.compensation_change_wizard` | `new_profile`, `edit_profile`, `toggle_profile_active`, `refresh` | `payroll_setup`, `payroll_calculation.runs`, `payroll_operations` |
| `payroll_calculation.assignments` | `payroll_calculation.assign_component` | `edit_assignment`, `toggle_assignment_active`, `refresh` | `payroll_setup`, `payroll_calculation.runs` |
| `payroll_calculation.inputs` | `payroll_calculation.input_batch_wizard` | `new_batch`, `open_batch`, `import_inputs`, `refresh` | `payroll_operations`, `payroll_calculation.runs` |
| `payroll_calculation.runs` | `payroll_calculation.payroll_run_wizard` | `new_run`, `calculate_run`, `approve_run`, `void_run`, `employee_detail`, `project_allocations` | `payroll_accounting`, `payroll_operations`, `payroll_setup` |

Notes:

- The `Payroll Run Wizard` should be the preferred path; `New Run`, `Calculate`, and `Approve` remain for expert fast-path use.
- Do not surface run-period filters in the ribbon. Those belong in the workspace.
- The runs surface should be the most context-sensitive payroll family because the dominant next action changes sharply across draft, calculated, approved, and employee-focus states.

## 3. Payroll Accounting

| Surface key | Primary action | Secondary actions | Related |
| --- | --- | --- | --- |
| `payroll_accounting.posting` | `payroll_accounting.posting_workbench` | `post_to_gl`, `posting_detail`, `open_validation`, `refresh` | `payroll_calculation`, `journals`, `fiscal_periods` |
| `payroll_accounting.payments` | `payroll_accounting.net_pay_settlement_wizard` | `record_payment`, `refresh` | `payroll_calculation`, `payroll_accounting.summary` |
| `payroll_accounting.remittances` | `payroll_accounting.remittance_wizard` | `new_batch`, `open_batch`, `add_line`, `cancel_batch`, `refresh` | `payroll_operations`, `payroll_accounting.summary` |
| `payroll_accounting.summary` | `payroll_accounting.open_full_summary` | `export_summary`, `refresh` | `payroll_calculation`, `payroll_operations`, `journals` |

Notes:

- Posting should stay separate from run preparation because many teams split payroll preparer and payroll accountant roles.
- `Posting Workbench` can begin as an evolved version of `PayrollPostRunDialog`.
- Posting and remittances should both switch surface variants based on selected object state, not just tab.

## 4. Payroll Operations

| Surface key | Primary action | Secondary actions | Related |
| --- | --- | --- | --- |
| `payroll_operations.validation` | `payroll_operations.readiness_wizard` | `run_assessment`, `open_check_detail`, `refresh` | `payroll_setup`, `payroll_calculation`, `payroll_accounting` |
| `payroll_operations.packs` | `payroll_operations.apply_statutory_pack` | `preview_rollover`, `refresh` | `payroll_setup`, `payroll_operations.validation` |
| `payroll_operations.imports` | `payroll_operations.payroll_import_wizard` | `preview_import`, `execute_import`, `download_template` | `payroll_setup`, `payroll_calculation` |
| `payroll_operations.print` | `payroll_operations.print_distribution_wizard` | `print_payslips`, `print_summary`, `export_payslips`, `save_pdf` | `payroll_calculation`, `payroll_accounting.summary` |
| `payroll_operations.audit` | `payroll_operations.export_audit` | `refresh` | `payroll_setup`, `payroll_calculation`, `payroll_accounting` |

Notes:

- Validation is important enough to deserve both a dashboard and a guided "fix what matters first" flow.
- Print and export are a workflow cluster, not just a few buttons.
- Validation should be one of the strongest examples of context awareness because the selected issue should change the dominant fix action.

---

## Wizard Strategy

### What should be a wizard

A payroll task should become a wizard when it:

- crosses multiple payroll tabs or workspaces
- creates or updates several records together
- requires readiness checks before commit
- needs preview, anomaly review, or approval
- benefits from resumability

### What should stay a child window

A payroll task should become a child window when it:

- is focused on one object or batch
- is data-dense and reviewed for several minutes
- needs its own ribbon and repeated actions
- is often opened from a register or workspace row

### What should stay a dialog

A payroll task should stay a modal dialog when it:

- is a short form
- is a one-shot confirm or data capture step
- does not justify its own long-lived workspace

---

## Recommended Payroll Wizards

### Wave 1

#### 1. Payroll Activation Wizard

Entry points:

- `payroll_setup.settings` ribbon
- empty-state cards in payroll setup

Steps:

1. Company payroll settings
2. Statutory pack selection or confirmation
3. Departments and positions
4. Component library seeding
5. Rule set seeding and bracket review
6. GL mapping and payroll payable readiness
7. First-period readiness summary

Why it should exist:

- today, setup is spread across settings, pack application, departments, positions, components, rules, and validation
- this is exactly the kind of multi-entity onboarding flow a wizard should own

#### 2. Employee Hire Wizard

Entry points:

- `payroll_setup.employees` ribbon
- employee empty-state card

Steps:

1. Identity
2. Employment details
3. Tax and CNPS profile
4. Payment account and payout method
5. Compensation profile
6. Recurring component assignments
7. First-period proration preview
8. Review and save

Why it should exist:

- the current employee form, compensation profile dialog, and assignment dialog are three separate work sessions
- a hire flow should leave the employee actually payroll-ready, not merely created

#### 3. Compensation Change Wizard

Entry points:

- `payroll_setup.employees`
- `payroll_calculation.profiles`
- employee-focused child windows

Steps:

1. Select employee and effective date
2. Change salary or compensation profile
3. Change recurring components
4. Preview retro and next-run impact
5. Approval note and save

Why it should exist:

- compensation changes are high-risk because effective dates and retro logic matter more than the raw form fields

#### 4. Payroll Run Wizard

Entry points:

- `payroll_calculation.runs`
- `payroll_operations.validation`

Steps:

1. Period and scope
2. Readiness scan
3. Variable input inclusion
4. Calculate run
5. Variance and anomaly review
6. Include or exclude employees with explanation
7. Approve run
8. Hand off to posting, printing, or return later

Why it should exist:

- this is the flagship payroll wizard already implied by `docs/Wizards.md`
- it can reuse existing services while giving users one coherent operator flow

#### 5. Remittance Wizard

Entry points:

- `payroll_accounting.remittances`
- `payroll_operations.validation` when remittance exposure is a blocker

Steps:

1. Select authority and period
2. Seed dues from posted payroll runs
3. Review lines, deadlines, and outstanding amounts
4. Create or update remittance batch
5. Hand off to payment tracking and close

Why it should exist:

- remittance work is deadline-driven and cross-cutting
- today the operator must mentally bridge posted runs, due lines, and batch state

### Wave 2

- Employee Offboarding Wizard
- Payroll Year-End Wizard
- Payroll Import Wizard if the universal import framework is not ready yet
- Payroll Print And Distribution Wizard if print/export grows beyond a simple dialog cluster

---

## Child Window Strategy

### Promote these into first-class child windows

| Current UI | Proposed child window key | Why |
| --- | --- | --- |
| `PayrollInputBatchDialog` | `child:payroll_input_batch` | table + toolbar + approval lifecycle already behaves like a workbench |
| `PayrollRunEmployeeDetailDialog` | `child:payroll_run_employee` | dense review surface with drill-down and related actions |
| `PayrollRunPostingDetailDialog` | `child:payroll_run_posting` | analysis-centric review window with accounting relevance |
| `PayrollSummaryDialog` or reporting summary window | `child:payroll_summary` | long-lived comparison and export surface |
| future run workbench window | `child:payroll_run` | would unify run review, employee list, and next actions |
| future remittance batch workbench | `child:payroll_remittance_batch` | batch state, lines, and payment actions fit the child-window model |

### Keep these as dialogs

| UI | Why it should stay a dialog |
| --- | --- |
| `CompanyPayrollSettingsDialog` | short form, bounded scope |
| `EmployeeFormDialog` | expert fast-path fallback even after hire wizard exists |
| `PayrollComponentFormDialog` | focused maintenance form |
| `PayrollRuleSetFormDialog` | focused maintenance form |
| `CompensationProfileDialog` | focused form for expert edits |
| `ComponentAssignmentDialog` | focused form for expert edits |
| `PayrollPaymentRecordDialog` | one-shot transaction capture |
| `PayrollRemittanceLineDialog` | single-line capture |

### Child-window ribbon surfaces

Recommended first child-window surfaces:

- `child:payroll_input_batch`
  - add_line / edit_line / delete_line / approve_batch / void_batch / close
- `child:payroll_run_employee`
  - payslip_preview / project_allocations / print / close
- `child:payroll_run_posting`
  - open_journal / export / print / close
- `child:payroll_summary`
  - export_pdf / export_csv / print / close
- `child:payroll_run`
  - calculate / approve / void / post / employee_detail / close
- `child:payroll_remittance_batch`
  - add_line / record_payment / mark_paid / cancel / close

---

## Naming And Command Design

Use workflow-shaped command names, not widget-shaped names.

Good:

- `payroll_setup.activation_wizard`
- `payroll_setup.hire_employee_wizard`
- `payroll_calculation.calculate_run`
- `payroll_accounting.remittance_wizard`

Avoid:

- `payroll_setup.btn_seed_click`
- `payroll_calculation.open_dialog`
- `payroll_operations.tab3_action`

The ribbon should express operator intent, not implementation detail.

For micro-surfaces, keep the command names stable even when the surface changes. The context should choose which commands are shown, not rename the same action every time.

---

## Engine Implications

The current ribbon engine supports:

- one active `surface_key`
- per-command enablement through `ribbon_state()`

That is a solid base, but true payroll context awareness will likely need one small extension:

- a host-level way to provide the **current context surface key**, not just the nav id

Good implementation options:

- extend the active page contract with `current_ribbon_surface_key()`
- or let payroll workspaces emit a shell signal when their internal focus context changes

If the engine stays exactly as-is, payroll can still get partway there by:

- swapping between multiple registered surface keys from the page
- using `refresh_active_state()` for lightweight enablement updates

If the engine is enhanced slightly, payroll can become properly context-aware without hacks.

---

## Recommended Related Navigation

Add payroll-specific related-page groupings:

- setup surfaces -> `payroll_calculation`, `payroll_operations`, `chart_of_accounts`
- calculation surfaces -> `payroll_setup`, `payroll_accounting`, `payroll_operations`
- accounting surfaces -> `payroll_calculation`, `journals`, `fiscal_periods`
- operations surfaces -> `payroll_setup`, `payroll_calculation`, `payroll_accounting`

Do not put deep fix links into every payroll surface. Reserve those for:

- wizard readiness steps
- validation detail windows
- posting workbench quick-fix areas

---

## Delivery Plan

### Slice P1 - Ribbon Infrastructure For Tabbed Payroll Workspaces

- add active payroll sub-context surface support
- wire tab change to ribbon surface swap
- register payroll setup and payroll calculation surfaces first

### Slice P2 - Child Windows For Dense Existing Payroll Dialogs

- promote input batch and run-employee detail to child windows
- add child ribbon surfaces for those windows

### Slice P3 - Payroll Activation Wizard

- orchestrate existing setup services and validation
- make this the default recommended entry point for new payroll companies

### Slice P4 - Employee Hire Wizard

- orchestrate employee, compensation, and assignment services
- keep existing dialogs as expert fallback

### Slice P5 - Payroll Run Wizard

- orchestrate create, calculate, anomaly review, approve
- hand off to accounting and print, but do not collapse every downstream role into one giant wizard

---

## Final Recommendation

Payroll should not be treated like a plain register page, and it should not be exempted from the ribbon either.

The right model is:

- tab-aware ribbon surfaces for payroll workspaces
- wizard-led orchestration for setup, hire, compensation change, runs, and remittances
- child windows for dense batch and drill-down work
- short dialogs kept for expert direct edits

That gives payroll a shell-level workflow language without flattening its real complexity.
