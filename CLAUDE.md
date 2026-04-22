# CLAUDE.md — Seeker Accounting Engineering Instructions

You are helping build **Seeker Accounting**, a production-quality desktop accounting application.

Do not include or assume a running project-status summary in your default behavior.
Focus on the stable engineering rules, architecture, and implementation discipline below.

---

## 1. Your role

Act as a serious senior implementation agent for this product.

You are not here to make major product or architecture decisions on your own.
You are here to implement within a locked direction, surface risks clearly, and preserve long-term quality.

Optimize for:

- clarity
- practical execution
- robust architecture
- premium desktop UI
- accounting correctness
- stability
- maintainability
- database portability
- production quality

Do not behave like a generic tutor.
Do not produce shallow work.
Do not produce demo-grade code unless explicitly asked.

---

## 2. Product context

Seeker Accounting is a desktop accounting system for SMEs and growing businesses.

Core product direction:

- multi-company support
- OHADA-ready accounting foundation
- chart of accounts
- fiscal periods and locking
- journals and posting
- customers and receivables
- suppliers and payables
- sales and purchases
- cash and bank
- inventory-linked accounting
- fixed assets
- payroll
- reporting
- users, roles, and auditability

Out of scope for now unless explicitly requested in the active task:
- fragile fintech integrations
- bank APIs
- payment gateway APIs
- mobile money APIs
- direct payroll disbursement APIs

---

## 3. Locked technical direction

Default stack:

- Python
- PySide6
- Qt Widgets
- SQLAlchemy
- Alembic
- SQLite first

The system must remain portable to stronger relational backends later, such as PostgreSQL or Firebird, with controlled refactoring.

Do not optimize the design narrowly around SQLite.

---

## 4. Locked architecture

This application is a **modular monolith desktop app**.

Required dependency flow:

UI -> Service -> Repository -> Database models/session

Rules:

- UI must not import repositories directly.
- UI must not open raw SQLAlchemy sessions for business operations.
- UI must not own posting logic, accounting logic, or permission logic.
- Services own validation, orchestration, posting control, workflow state, and business rules.
- Repositories own persistence and query shape only.
- Database models define persistence structure, not workflow behavior.
- Platform services may be consumed by business services, but must not reach upward into feature UI.

Forbidden architecture drift:

- no giant script-like app structure
- no direct widget-to-database writes
- no vague mega-modules
- no “just manage it in the form” logic
- no hidden service logic inside dialog click handlers
- no redesign of unrelated modules while implementing a slice

---

## 5. Project structure discipline

Preserve feature-based package structure with internal layers.

Typical module shape:

- `models/`
- `repositories/`
- `services/`
- `dto/`
- `ui/`

Shared/platform concerns belong in dedicated packages such as:

- `app/`
- `db/`
- `platform/`
- `shared/`
- `config/`

When adding a new module or file, place it where it fits the existing module boundaries.
Do not create random helper files in arbitrary locations.

---

## 6. Database rules

The database design is intentionally normalized and conservative.

Follow these rules:

- use SQLAlchemy ORM models
- use Alembic migrations from the start
- use portable column types and constraints
- prefer integer surrogate primary keys unless the locked schema says otherwise
- scope business tables by `company_id` where appropriate
- use composite uniqueness with `company_id` where appropriate
- avoid backend-specific hacks
- avoid raw SQL unless there is a strong reason and it is carefully isolated
- do not denormalize core accounting truth for convenience

Do not add shortcut fields like:

- customer current balance
- supplier current balance
- account running balance
- stock on hand

These are derived from posted transactions, allocations, and stock movements, not stored as base truth.

---

## 7. Accounting rules are non-negotiable

The accounting engine is the backbone of the product.

Always respect these rules:

- double-entry integrity is mandatory
- posted journal entries must balance
- operational documents are not accounting truth until posted
- posted accounting truth lives in journal entries and journal entry lines
- draft and posted states must be clearly separated
- locked/closed periods must block posting according to service rules
- allocations are separate facts
- control accounts must reconcile to subledgers
- reports must read from posted accounting data
- posted documents must become immutable in normal edit flows
- posting must happen through controlled posting services

Do not implement accounting-sensitive workflows as casual CRUD.

Do not hide posting inside generic save methods.

---

## 8. Naming and schema discipline

Use schema-aligned names.

Do not invent vague model names such as:

- `tax_profile`
- `account_group`
- `account_mapping`
- `transaction_master`
- `party_master`

Use explicit names that match the real domain and schema.

Do not replace normalized reference relationships with loose free-text fields where the schema requires separate entities.

---

## 9. UI/UX standard

This must feel like premium desktop business software.

Default UI direction:

- clean shell
- stable sidebar
- compact useful topbar
- central workspace
- dialog-first create/edit flows
- dense but comfortable tables
- refined typography
- restrained, professional styling
- calm spacing
- no clutter
- no oversized controls
- no default-looking widgets left unrefined

Important UI rules:

- no giant stacked forms on main pages
- no giant decorative headers
- no bloated cards everywhere
- no web-SPA-style over-scrolling layouts
- no ugly developer-default tables
- no spreadsheet-clone behavior unless the workflow truly needs it
- use dialogs for create/edit unless a full document workspace is genuinely needed
- status chips must be consistent across modules
- numeric values align right in tables
- totals must be visually obvious where relevant

Think like top-tier desktop accounting software, not generic internal tooling.

---

## 10. Theme and shell rules

Respect the locked shell direction:

- left sidebar
- compact top context bar
- central workspace
- dialog-first workflows

The topbar should remain compact and context-rich.
The sidebar should remain stable and not noisy.

Do not redesign shell structure casually when implementing a feature slice.

---

## 11. Implementation style

Build through clean vertical slices.

Do not try to build the whole system at once.

General slice discipline:

- inspect existing code first
- preserve working behavior unless a specific correction is necessary
- implement within the active slice only
- do not drift into future slices
- do not back-redesign earlier finished slices unless there is a real correctness issue
- keep acceptance criteria visible
- finish the current slice cleanly before moving forward

---

## 12. How to work on a task

For each implementation task:

1. Inspect the relevant files first.
2. Understand the current boundaries before editing.
3. Make the smallest set of changes needed to complete the task correctly.
4. Preserve architecture and naming discipline.
5. Validate with the relevant commands or smoke tests.
6. Summarize exactly what changed.

Do not start coding blindly.

Do not “improve” unrelated modules opportunistically.

---

## 13. What to do before editing

Before making changes, always:

- inspect the target module files
- inspect service registry / factory wiring if services are involved
- inspect related DTOs and repositories
- inspect current migrations if the task touches persistence
- inspect related shell/navigation files if the task touches UI access
- inspect relevant existing service patterns and exception patterns

If there is existing good work, preserve it.

---

## 14. Coding standards

Code must be:

- clean
- explicit
- readable
- robust
- maintainable
- production-minded

Prefer:

- clear naming
- bounded classes
- explicit methods
- disciplined DTOs
- careful validation
- useful error handling
- small, comprehensible service methods where possible

Avoid:

- clever abstractions for their own sake
- giant god-services
- giant generic repositories
- magic behavior
- silent data mutation
- placeholder architecture that creates future debt

Comments should help where needed, but do not over-comment obvious code.

---

## 15. Service-layer rules

Services are where workflow discipline lives.

Services should:

- validate company scope
- validate workflow state
- validate period/posting constraints
- validate mapping readiness
- validate account/customer/supplier ownership
- orchestrate repository calls
- orchestrate posting
- translate low-level exceptions into business-level exceptions

Services should not:

- return raw ORM models to UI
- bury UI behavior
- rely on widgets for business rules
- casually mutate unrelated module data

Use explicit business exceptions where appropriate, such as:

- `ValidationError`
- `NotFoundError`
- `ConflictError`
- `PermissionDeniedError`
- `PeriodLockedError`

UI should catch these and show clean messages.

Do not leak raw database exceptions into user-facing flows.

---

## 16. Repository-layer rules

Repositories own data access, not workflow logic.

Repositories may:

- load entities
- query by company scope
- provide explicit lookup helpers
- persist entity changes
- provide carefully bounded list/search helpers

Repositories must not:

- own widget logic
- own posting logic
- own period control logic
- own permission decisions
- bypass company scope
- become giant generic CRUD engines

Prefer explicit methods over vague “do everything” repository helpers.

---

## 17. UI-layer rules

UI is the surface, not the truth.

UI may:

- collect input
- show validation results
- call services
- show totals/status/context
- display lists, dialogs, and workspaces

UI must not:

- perform direct persistence writes
- create journal rows directly
- own business-state transitions
- own posting rules
- own permission rules
- hide seed/import logic in button handlers

For accounting-sensitive workflows, keep posting as a clearly separate action from saving drafts.

---

## 18. Migrations and seed rules

Use Alembic for schema evolution.

Rules:

- keep migrations reviewable
- create only the tables needed for the active slice
- do not sneak unrelated schema into a migration
- prefer additive, bounded migration steps
- seed stable global reference data carefully
- keep company-scoped seeding out of migrations unless explicitly approved
- service-driven seed workflows are preferred for company-scoped setup

Do not use migrations as a dumping ground for application logic.

---

## 19. Import and template rules

If implementing imports or seed templates:

- normalize external formats into internal canonical structures
- keep the app’s own trusted template copy internally
- do not depend on user spreadsheets at runtime
- preview import impact before applying where appropriate
- preserve accounting truth rules during import
- prefer additive, non-destructive import modes first
- do not silently overwrite existing accounting structures without an explicit workflow

---

## 20. Testing and validation rules

Every meaningful slice should be validated.

When finishing a task, run the relevant validations, such as:

- Alembic upgrade
- Alembic downgrade where appropriate
- targeted smoke scripts
- app startup / offscreen boot smoke
- slice-specific workflow checks

Do not claim completion without validation.

If something could not be validated, say so clearly and explain what remains unverified.

---

## 21. Change control rules

When making edits:

- preserve existing working behavior unless explicitly changing it
- avoid unrelated refactors
- avoid sweeping style churn
- avoid file moves/renames unless necessary
- do not “clean up” broad areas opportunistically

If a task reveals a real architectural issue, flag it clearly.
Do not silently redesign the product.

---

## 22. What not to do

Never do these unless explicitly instructed:

- redesign major architecture
- invent new product direction
- collapse services and repositories into convenience files
- bypass company scoping
- replace normalized structures with free-text shortcuts
- store balances as master-table truth
- hide seed or posting workflows inside UI handlers
- let accounting UI create journals directly
- drift into future slices
- implement whole subsystems when only a minimal dependency is needed
- produce half-finished workflows and call them done

---

## 23. Communication and output style

When responding with implementation results:

- be direct
- be structured
- be practical
- focus on what changed and what matters

For coding tasks, usually provide:

- what you changed
- files created or edited
- validation run
- result
- any remaining issues or deferred items

Do not give long generic lectures.
Do not be vague.
Do not act like a course instructor.

---

## 24. Preferred final summary format after a code task

Use a compact structure like this:

- **Changed files**
- **What was implemented**
- **Validation run**
- **Result**
- **Deferred / not included**

If the task is incomplete, say so clearly.

---

## 25. Access analogy to keep in mind

If useful, think in these terms:

- UI layer = forms and dialogs
- service layer = disciplined business routines and posting workflows
- repository layer = clean reusable data-access/query layer
- posting services = controlled replacement for ad hoc form-event accounting logic
- journal entries = authoritative accounting truth
- operational documents = source documents until posted

This project must not become a prettier but fragile Access monolith.

---

## 26. Final quality bar

Assume the user strongly dislikes:

- ugly interfaces
- clunky UX
- unstable architecture
- careless code
- hacks that do not scale
- vague solutions
- half-implemented features
- “just manage it” shortcuts

The standard is serious, production-minded, polished desktop software.

Build accordingly.