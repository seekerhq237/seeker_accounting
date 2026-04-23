# Contracts, Projects, and Jobs Ribbon + Wizard Blueprint

## Purpose

This document locks the intended command-band, child-workspace, and wizard design for the contracts, projects, and jobs slice.

It is grounded in four existing constraints:

- `docs/Wizards.md`: wizards are service-driven orchestrations, not decorative multi-step forms.
- `docs/specs docs/ribbon_context_plan.md`: ribbons are context surfaces keyed by page or child window.
- `docs/seeker_ui_style_guide.md`: list pages stay lean; document-like work happens in child workspaces; dialogs stay compact.
- the current module code under `modules/contracts_projects/`, `modules/job_costing/`, `modules/budgeting/`, and `modules/management_reporting/`.

The goal is not to add more buttons. The goal is to separate scanning, structuring, planning, approval, and analysis into the right surfaces.

---

## Design Conclusions From The Existing Docs

### 1. Wizards must own orchestration, not simple CRUD

The wizard document is explicit: a wizard should be resumable, service-driven, previewable, and used for cross-entity setup or high-risk workflow.

That means:

- creating a single contract is not automatically a wizard
- building a contract, linked project, initial WBS, control defaults, and first budget version is a wizard
- revising a budget across jobs and cost codes with impact preview is a wizard
- closing a project with commitments, remaining budget, and margin consequences is a wizard

### 2. Register ribbons must stay narrow

The ribbon plan and style guide both point toward dense register pages with a focused action band.

That means the main `contracts` and `projects` ribbons should not become giant launch pads for every subordinate dialog.

They should do four things well:

- create
- open the selected record into a richer workspace
- advance lifecycle state
- jump to the most relevant analysis or related surface

### 3. Complex project work should move into child workspaces

The current code already shows that projects are not a single-form entity:

- jobs are hierarchical and status-driven
- budget versions have draft or submitted or approved workflow
- commitments have draft or approved or closed workflow
- contracts accumulate financial effect through change orders

Those are not lightweight dialog actions anymore. They are workbenches.

### 4. Company-scoped controls must not masquerade as project-scoped actions

One important design correction from the current surface:

- `Cost Codes` are company-scoped, not project-scoped

They can still be reachable from the projects module, but they should be presented as a library or controls surface, not as if each project owns its own cost-code set.

### 5. Jobs should not become a top-level sidebar page yet

The current domain model is `Contract -> Project -> Job -> Cost Code`.

Jobs belong inside project context. They deserve a serious child workspace, not a detached top-level module page in the first wave.

---

## Surface Model

This slice should use four surface types.

### A. Register pages

Use for scanning and selecting records.

Surfaces:

- `contracts`
- `projects`

### B. Child workspaces with ribbons

Use when the user is working inside one selected record and needs multiple coordinated commands or subordinate structures.

Recommended child surface keys:

- `child:contract_workspace`
- `child:contract_change_orders`
- `child:contract_change_order`
- `child:project_workspace`
- `child:project_jobs`
- `child:project_job`
- `child:project_budget_versions`
- `child:project_budget_version`
- `child:project_commitments`
- `child:project_commitment`
- `child:project_cost_codes`

### C. Compact dialogs with local toolbar strip only

Use for light forms with no meaningful substructure.

Keep as dialogs initially:

- quick create or edit contract when used as a shortcut flow
- quick create or edit project when only basic fields are needed
- quick create or edit job
- quick create or edit cost code
- budget line editor
- commitment line editor

If a dialog starts needing its own status workflow, preview pane, or sub-grid, promote it to a child workspace.

### D. Wizards

Use for cross-entity setup, planning, revision, or close processes where the system should validate prerequisites and preview downstream effect.

---

## Core Interaction Rule

The register ribbon should launch the right deeper surface instead of carrying every command itself.

The intended user flow is:

1. select contract or project in the register
2. use `Open Workspace` or double-click
3. do structural work inside the child workspace ribbon
4. use wizards only for setup, revision, or closure workflows

This keeps the top command band stable and prevents the contracts/projects pages from turning into button farms.

---

## Contracts Ribbon Design

### Role of the `contracts` page

The contracts page is a commercial register:

- contract identity
- client
- type
- base amount and derived value awareness
- status
- quick access to change and summary workflows

It is not the right place to manage every change order, linked project, and billing nuance inline.

### Recommended ribbon groups for `contracts`

#### Group 1. Start

- `contracts.new` -> `New Contract`
- `contracts.wizard` -> `Contract Kickoff Wizard`
- `contracts.open_workspace` -> `Open Workspace`

Notes:

- `New Contract` remains the quickest path for experienced users.
- `Contract Kickoff Wizard` is the safe path when the commercial setup should immediately flow into project execution.
- `Open Workspace` becomes the normal path after selection.

#### Group 2. Lifecycle

- `contracts.edit` -> `Edit Basics`
- `contracts.activate` -> `Activate`
- `contracts.hold` -> `Put On Hold`
- `contracts.complete` -> `Complete`
- `contracts.close` -> `Close`
- `contracts.cancel` -> `Cancel`

Design note:

The current page only exposes activate and cancel. The ribbon should reserve space for the full lifecycle because the schema already distinguishes `draft`, `active`, `on_hold`, `completed`, `closed`, and `cancelled`.

If the service layer has not implemented every state yet, ship the buttons disabled until the workflow exists instead of redesigning the band later.

#### Group 3. Change And Commercial Control

- `contracts.change_orders` -> `Change Orders`
- `contracts.new_change_order` -> `New Change Order`
- `contracts.revenue_recognition` -> `Revenue Recognition`

Design note:

`Change Orders` should open the selected contract's dedicated child workspace. The list page should not try to host submission and approval behavior directly.

#### Group 4. Analysis

- `contracts.summary` -> `Contract Summary`
- `contracts.open_projects` -> `Linked Projects`
- `contracts.refresh` -> `Refresh`
- `contracts.export_list` -> `Export List`

### Recommended command order for the live register ribbon

Use this order in the actual band:

1. `New Contract`
2. `Contract Kickoff Wizard`
3. `Open Workspace`
4. divider
5. `Edit Basics`
6. `Activate`
7. `Put On Hold`
8. `Close`
9. `Cancel`
10. divider
11. `Change Orders`
12. `Contract Summary`
13. divider
14. `Refresh`
15. `Export List`

### What should not stay on the top contract ribbon

Do not put these on the register ribbon in the first wave:

- direct approval buttons for a selected change order
- linked-project structural editing
- billing schedule grid editing
- revenue-recognition detail editing

Those belong in child workspaces or wizards.

---

## Contract Child Windows And Their Ribbons

### 1. `child:contract_workspace`

This should replace the idea that a contract is just a flat dialog.

#### Why it deserves a child workspace

A serious contract surface needs to show:

- identity and lifecycle state
- customer and billing basis
- linked projects
- current value derived from approved change orders
- change-order history
- revenue-recognition or billing readiness shortcuts
- contract summary access

#### Workspace structure

- top identity strip: contract number, customer, type, status, dates, base value, current value
- left or main body: contract basics and commercial terms
- lower panel or secondary grid: linked projects
- right summary dock: base amount, approved deltas, current value, retention, margin signals where available

#### Ribbon

Group 1. Record

- `contract_workspace.save`
- `contract_workspace.save_and_close`
- `contract_workspace.print`

Group 2. Lifecycle

- `contract_workspace.activate`
- `contract_workspace.hold`
- `contract_workspace.complete`
- `contract_workspace.close`
- `contract_workspace.cancel`

Group 3. Structure

- `contract_workspace.change_orders`
- `contract_workspace.new_linked_project`
- `contract_workspace.open_linked_project`

Group 4. Analysis

- `contract_workspace.summary`
- `contract_workspace.revenue_plan`

The ribbon should make the contract workspace feel like a commercial control surface, not a generic edit form.

### 2. `child:contract_change_orders`

This should evolve from the current list dialog into a change-management workbench.

#### Why

The current dialog already implies workflow state and financial effect:

- draft
- submitted
- approved
- rejected
- cancelled

That is enough complexity to justify a ribboned child surface.

#### Ribbon

Group 1. Record

- `contract_change_orders.new`
- `contract_change_orders.edit`
- `contract_change_orders.open`

Group 2. Workflow

- `contract_change_orders.submit`
- `contract_change_orders.approve`
- `contract_change_orders.reject`
- `contract_change_orders.cancel`

Group 3. Analysis

- `contract_change_orders.preview_impact`
- `contract_change_orders.refresh`

#### Important addition

Approvals and rejections should capture a reason before commit. The current button set is too thin for an auditable change-control workflow.

### 3. `child:contract_change_order`

Use when a single change order is opened for detailed work.

#### Ribbon

- `Save`
- `Save & New`
- divider
- `Submit`
- `Approve`
- `Reject`
- `Cancel`
- divider
- `Impact Preview`
- `Close`

The preview is important. A change order is not just text and amount; it changes contract value, possibly project dates, and later project margin.

---

## Projects Ribbon Design

### Role of the `projects` page

The projects page is the execution register.

It should answer:

- what projects exist
- which ones are active or at risk
- which project should I open to manage structure, budget, or commitments

It should not be the place where the user performs every detailed planning action from one crowded strip.

### Recommended ribbon groups for `projects`

#### Group 1. Start

- `projects.new` -> `New Project`
- `projects.wizard` -> `Project Setup Wizard`
- `projects.open_workspace` -> `Open Workspace`

#### Group 2. Lifecycle

- `projects.edit` -> `Edit Basics`
- `projects.activate` -> `Activate`
- `projects.hold` -> `Put On Hold`
- `projects.complete` -> `Complete`
- `projects.close` -> `Close`
- `projects.cancel` -> `Cancel`

#### Group 3. Workbench Access

- `projects.jobs` -> `Jobs`
- `projects.budgets` -> `Budgets`
- `projects.commitments` -> `Commitments`
- `projects.cost_code_library` -> `Cost Code Library`

Design note:

Rename the current mental model from `Cost Codes` to `Cost Code Library` whenever launched from the projects surface. That makes the company scope clear.

#### Group 4. Analysis

- `projects.variance` -> `Variance`
- `projects.profitability` -> `Profitability`
- `projects.contract_summary` -> `Contract Summary`
- `projects.refresh` -> `Refresh`
- `projects.export_list` -> `Export List`

### Recommended command order for the live register ribbon

1. `New Project`
2. `Project Setup Wizard`
3. `Open Workspace`
4. divider
5. `Edit Basics`
6. `Activate`
7. `Put On Hold`
8. `Close`
9. `Cancel`
10. divider
11. `Jobs`
12. `Budgets`
13. `Commitments`
14. divider
15. `Variance`
16. `Refresh`
17. `Export List`

### What should move off the main project ribbon

Avoid forcing the register ribbon to carry:

- individual budget-version state transitions
- commitment approval buttons
- WBS restructuring commands
- line-level editing actions

Those belong in project child workspaces.

---

## Project Child Windows And Their Ribbons

### 1. `child:project_workspace`

This is the anchor child window for the entire slice.

If only one rich child workspace is built first, it should be this one.

#### Why it matters

The project is the point where all management-accounting structures converge:

- contract link
- manager and control defaults
- jobs
- budget versions
- commitments
- actual costs
- variance analysis

#### Workspace structure

- identity strip: code, name, status, manager, contract, customer, currency, control mode
- main form zone: editable project basics
- lower tabs or stacked panes: Jobs, Budgets, Commitments, Activity
- right dock: budget vs actual vs committed vs remaining, key dates, alert chips

#### Ribbon

Group 1. Record

- `project_workspace.save`
- `project_workspace.save_and_close`
- `project_workspace.print`

Group 2. Lifecycle

- `project_workspace.activate`
- `project_workspace.hold`
- `project_workspace.complete`
- `project_workspace.close`
- `project_workspace.cancel`

Group 3. Structure

- `project_workspace.jobs`
- `project_workspace.budgets`
- `project_workspace.commitments`
- `project_workspace.cost_code_library`

Group 4. Analysis

- `project_workspace.variance`
- `project_workspace.actuals`
- `project_workspace.profitability`
- `project_workspace.contract`

This workspace should be the command hub. The register ribbon should feel lean because this child ribbon exists.

### 2. `child:project_jobs`

This should become a proper WBS workbench, not just a flat maintenance dialog.

#### Why

The schema supports hierarchy through `parent_job_id`, but the current list is effectively a flat manager. That leaves value on the table.

#### Workspace structure

- left: job tree with expand or collapse
- center: selected job details and dates
- lower panel: budget and actual rollups for selected job
- optional right panel: advisor messages like direct-posting risk or missing budget coverage

#### Ribbon

Group 1. Create

- `project_jobs.new_job`
- `project_jobs.new_child_job`
- `project_jobs.edit`

Group 2. Structure

- `project_jobs.reparent`
- `project_jobs.move_up`
- `project_jobs.move_down`
- `project_jobs.import_wbs`

Group 3. Lifecycle

- `project_jobs.deactivate`
- `project_jobs.reactivate`
- `project_jobs.close_job`

Group 4. Analysis

- `project_jobs.view_actuals`
- `project_jobs.view_budget_coverage`
- `project_jobs.expand_all`
- `project_jobs.collapse_all`

#### Important design decision

Use a tree-first presentation, not another flat register, because the job model already encodes hierarchy and summary nodes.

### 3. `child:project_job`

Keep this as a lightweight child document only if job editing starts needing a richer detail view. If not, keep it as a compact dialog.

If promoted, use this ribbon:

- `Save`
- `Save & New Sibling`
- `Save & New Child`
- divider
- `Deactivate`
- `Reactivate`
- `Close Job`
- divider
- `View Actuals`
- `Close`

### 4. `child:project_budget_versions`

The current budget version dialog already behaves like a workflow surface and should be planned that way.

#### Ribbon

Group 1. Record

- `project_budget_versions.new`
- `project_budget_versions.edit`
- `project_budget_versions.open_lines`
- `project_budget_versions.clone`

Group 2. Workflow

- `project_budget_versions.submit`
- `project_budget_versions.approve`
- `project_budget_versions.cancel`

Group 3. Analysis

- `project_budget_versions.preview_variance`
- `project_budget_versions.refresh`

#### Child window note

The budget lines editor should eventually become a `child:project_budget_version` document workspace with header plus lines grid. That is closer to the document template in the style guide than the current nested list dialog.

### 5. `child:project_commitments`

This is another workflow workbench, not a simple maintenance list.

#### Ribbon

Group 1. Record

- `project_commitments.new`
- `project_commitments.edit`
- `project_commitments.open_lines`

Group 2. Workflow

- `project_commitments.approve`
- `project_commitments.close`
- `project_commitments.cancel`

Group 3. Analysis

- `project_commitments.preview_budget_headroom`
- `project_commitments.refresh`

#### Child window note

The commitment header plus lines pattern maps cleanly to the document workstation template and should eventually be upgraded into a child document ribbon, not left as a modal maintenance stack.

### 6. `child:project_cost_codes`

This surface is a register library, not a selected-project child document.

Use it from the projects module, but visually label it as a company control surface.

#### Ribbon

- `New Cost Code`
- `Edit`
- `Deactivate`
- `Reactivate`
- divider
- `Cost Code Activation Wizard`
- `Refresh`
- `Export List`

---

## Wizard Catalog For This Slice

The current `Wizards.md` already names three relevant items:

- Project Setup Wizard
- Revenue Recognition Wizard
- Project Close Wizard

That list is directionally right, but too thin for the actual module complexity already visible in code.

Below is the recommended catalog for this slice.

### Wave 1. Flagship wizards

#### 1. Project Setup Wizard

This should be the first serious wizard for this slice.

Launch from:

- `projects` register
- `contracts` register when a contract is selected
- empty state on the projects page

Why it matters:

- it crosses contract, project, job, budget-control, and cost-structure boundaries
- it prevents bad setup before costs begin posting
- it aligns directly with the wizard architecture document

Recommended steps:

1. Project mode
2. Contract and customer linkage
3. Identity, manager, dates, currency
4. Control defaults and posting requirements
5. WBS or jobs template
6. Cost code bundle
7. Initial budget shell
8. Commit preview and readiness report

Advisor panel should detect:

- missing contract/customer coherence
- missing manager
- no posting job that allows direct costs
- hard-stop control with no initial budget version
- jobs with no cost-code coverage

#### 2. Contract Kickoff Wizard

This should be the commercial entry wizard, not just a prettier contract form.

Launch from:

- `contracts` register
- command palette

Recommended steps:

1. Contract mode and template
2. Customer and commercial identity
3. Value, currency, billing basis, retention, dates
4. Linked project decision: create new or link existing
5. Change-order governance defaults
6. Revenue or billing readiness summary
7. Commit preview

The key idea is that the wizard can optionally create the first linked project immediately instead of leaving the user to do disconnected setup in two places.

#### 3. Job Structure Wizard

Launch from:

- `child:project_jobs`
- `child:project_workspace`

Recommended steps:

1. Choose template or import source
2. Define phase levels
3. Create summary and posting jobs
4. Set dates and sequence
5. Validate hierarchy and posting rules
6. Preview tree and apply

This wizard matters because the current model supports hierarchy, but the current UI does not exploit it.

### Wave 2. Planning and revision wizards

#### 4. Budget Build And Revision Wizard

Launch from:

- `child:project_budget_versions`
- `child:project_workspace`

Recommended steps:

1. Choose source version or build mode
2. Choose job and cost-code scope
3. Apply distribution logic
4. Add contingency and allowances
5. Compare to prior version
6. Submit or save draft

This should absorb the current clone flow and go beyond it.

#### 5. Change Order Impact Wizard

Launch from:

- `child:contract_change_orders`
- `child:contract_workspace`

Recommended steps:

1. Identify scope, price, time, or mixed change
2. Enter commercial deltas
3. identify linked project and schedule impact
4. preview revised contract value and margin effect
5. submit for approval or save draft

This should feel like controlled commercial change management, not a raw edit dialog.

#### 6. Cost Code Activation Wizard

Launch from:

- `child:project_cost_codes`
- `projects` register empty or first-run state

Recommended steps:

1. Pick industry bundle or company template
2. review codes and types
3. assign default GL mappings
4. detect duplicates or inactive conflicts
5. apply as company library

This is smaller than the project setup wizard, but high leverage because it standardizes later budgeting and actual-cost analysis.

### Wave 3. Close and recognition wizards

#### 7. Revenue Recognition Wizard

Launch from:

- `child:contract_workspace`
- `child:project_workspace`

Recommended steps:

1. Select recognition method
2. select source scope
3. preview recognition schedule
4. preview accounting effect
5. commit through posting service

#### 8. Project Close Wizard

Launch from:

- `projects` register
- `child:project_workspace`

Recommended steps:

1. status and prerequisite scan
2. open commitments review
3. unresolved budget variance review
4. final actuals and job closure scan
5. margin summary
6. close preview and commit

Advisor should explicitly flag:

- open commitments
- active jobs still allowing cost posting
- unapproved latest budget
- missing final variance review

#### 9. Contract Close Or Renewal Wizard

Launch from:

- `contracts` register
- `child:contract_workspace`

Recommended steps:

1. linked projects status scan
2. open change-order scan
3. revenue-recognition completion scan
4. final value and margin review
5. choose close or renew path

---

## Which Existing Dialogs Should Stay Dialogs

Not every form should become a ribboned child window.

Keep these compact unless scope expands materially:

- contract quick create or edit
- project quick create or edit
- job quick create or edit
- cost code quick create or edit
- budget line editor
- commitment line editor

For these, use the style-guide rule:

- local `ToolbarStrip` in dialog mode
- bottom action rail for `Save`, `Cancel`, `Close`

Do not register a shell ribbon surface for tiny edit dialogs unless they become genuine child documents.

---

## Related-Page Navigation Recommendations

Keep related links deliberately tight.

Recommended additions to the related-pages spec:

- `contracts` -> `projects`, `contract_summary`, `customers`
- `projects` -> `contracts`, `project_variance_analysis`, `contract_summary`
- `child:project_workspace` -> `project_variance_analysis`, `contract_summary`
- `child:contract_workspace` -> `projects`, `contract_summary`

Avoid turning related links into a module-wide jump menu.

---

## Practical Design Corrections To The Current UI

### 1. Replace toolbar crowding with ribbon plus workspace layering

The current `ProjectsPage` mixes:

- project record actions
- company library access
- planning surfaces
- execution surfaces

in a single inline toolbar.

That is exactly what the ribbon plus child-workspace design should fix.

### 2. Make jobs visibly hierarchical

The schema already supports hierarchy. The jobs UI should look like WBS management, not reference-list maintenance.

### 3. Treat budgets and commitments as mini-documents

Their status workflows already justify document-like child workspaces and ribbons.

### 4. Capture reasons on irreversible or sensitive state transitions

At minimum, design for reason capture on:

- reject change order
- cancel change order
- close job
- cancel budget version
- close or cancel commitment
- close project
- close contract

### 5. Show derived truth clearly

For contracts in particular:

- base contract amount is not the same as current contract value
- current value is derived from approved change orders

That distinction should appear in the workspace layout and in the advisor panel for any relevant wizard.

---

## Recommended First Delivery Sequence

If this slice is implemented incrementally, use this order.

### Slice CP-R1. Register ribbons

Deliver:

- `contracts` ribbon
- `projects` ribbon
- `Open Workspace` entry points
- related-page links for contract summary and project variance

Goal:

stop the top-level pages from depending on crowded inline button rows

### Slice CP-R2. Project workspace

Deliver:

- `child:project_workspace`
- project ribbon as the structural command hub

Goal:

give the most complex record in the module a proper home

### Slice CP-W1. Project Setup Wizard

Deliver:

- flagship project wizard
- readiness and preview pattern for this slice

Goal:

prove the wizard framework on a workflow that genuinely benefits from it

### Slice CP-R3. Jobs workbench

Deliver:

- `child:project_jobs`
- tree-based WBS workspace

Goal:

make the hierarchy model real in the UI

### Slice CP-R4. Contract workspace and change-order workbench

Deliver:

- `child:contract_workspace`
- `child:contract_change_orders`

Goal:

separate commercial control from project execution while keeping the two connected

### Slice CP-W2. Budget, change-order, and close wizards

Deliver next:

- Budget Build And Revision Wizard
- Change Order Impact Wizard
- Project Close Wizard

---

## Final Position

The right design is not:

- one huge projects ribbon full of every deep command
- one huge wizard that tries to do every contract and project task forever
- dozens of modal dialogs with local button rows and no durable command model

The right design is:

- lean register ribbons
- serious child workspaces for contract and project control
- a tree-first jobs workbench
- wizard entry only where orchestration and preview actually matter

If we hold that line, the contracts/projects/jobs slice will feel like premium desktop management accounting software instead of a cluster of maintenance dialogs.
