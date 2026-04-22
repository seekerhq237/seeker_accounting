# Sage UI Benchmark Audit

## Purpose

Study the supplied Sage screenshots and identify why the UI feels more disciplined than Seeker's current shell and document screens.

This is not about copying Sage pixel-for-pixel.

It is about understanding the design grammar that makes Sage feel:

- precise
- calculated
- operational
- trustworthy
- fast to scan

## Core Finding

Sage does **not** feel stronger because it is more decorative.

It feels stronger because it is:

- stricter about layout zones
- tighter in spacing
- flatter in surfaces
- denser in information
- clearer in action hierarchy
- more consistent in document-entry structure

Seeker currently feels more like a modern generic business app.

Sage feels like a purpose-built accounting workstation.

That difference is the real gap.

## What Sage Is Doing Well

## 1. The Shell Has Hard Geometry

Across the screenshots, Sage keeps the shell in rigid bands:

- top application menu
- top ribbon/action bar
- left navigation rail
- main work surface
- optional side list/action pane
- bottom status bar

Each region has a fixed job.

Nothing feels like a floating convenience layer. Everything belongs to a clear operational rail.

This creates:

- fast orientation
- low visual ambiguity
- strong muscle memory

## 2. Surfaces Are Flat, Not Puffy

Sage uses:

- low or zero border radius
- thin borders
- light gray backgrounds
- restrained color blocks
- minimal shadows

The result is a UI that feels measured and industrial.

Seeker currently uses many rounded cards, soft fills, and "friendly SaaS" surfaces. That makes the product feel softer and less exact than the benchmark.

## 3. Density Is Controlled, Not Cramped

Sage is dense, but not chaotic.

It achieves this through:

- compact controls
- compact headers
- narrow but deliberate spacing
- strong alignment
- fewer visual motifs

Important detail:

Sage does **not** use large empty breathing areas to create order. It uses structure.

## 4. Information Hierarchy Is Operational

Sage gives the eye a clear order:

1. current module/location
2. actions available here
3. current list or document
4. status or totals
5. secondary options

This is why it feels "professional" even when visually plain.

The user always knows:

- where they are
- what they can do next
- what the current record state is

## 5. Documents Are Built Like Workstations

The purchase order and document capture screenshots show a very stable document grammar:

- title/tool row at top
- compact metadata fields near top
- one dominant data grid
- totals grouped tightly
- actions pinned to predictable corners

This is critical.

Sage does not treat transaction entry as a general form.
It treats it as a work surface.

That is a major place where Seeker is still behind.

## 6. Color Is Functional, Not Atmospheric

Sage uses color mostly for:

- selected module
- action emphasis
- status
- chart segmentation

Most of the UI is neutral.

That means when color appears, it means something.

Seeker currently spends too much visual energy on surface styling and not enough on functional contrast.

## 7. Lists and Tables Feel Authoritative

The Sage tables have:

- compact rows
- strong header contrast
- clean vertical reading rhythm
- obvious status cells
- link-like row actions

The tables feel like the center of the product.

That matters in accounting software.

In this category, tables are not supporting UI. They are the main UI.

## What Seeker Is Currently Doing

## 1. Seeker Uses a Soft Web-App Vocabulary

Current shell/style signals from:

- `src/seeker_accounting/shared/ui/styles/tokens.py`
- `src/seeker_accounting/shared/ui/styles/palette.py`
- `src/seeker_accounting/shared/ui/styles/qss_builder.py`

show a design language based on:

- large radii
- soft cards
- light-blue accent surfaces
- chip-style controls
- roomy padding

This is coherent, but it pushes Seeker toward "pleasant SaaS dashboard" instead of "precision accounting workstation".

## 2. The Top Bar Is Generic, Not ERP-Structured

From:

- `src/seeker_accounting/app/shell/topbar.py`

the top bar is organized like a modern product shell:

- sidebar toggle
- company switcher
- `New`
- search
- theme
- bell
- fiscal chip
- license chip
- profile

This is useful, but it is not as structurally disciplined as Sage's:

- top text menu
- ribbon/action layer
- context-specific commands

Seeker's top bar is trying to be universal.
Sage's top band is operational and location-specific.

## 3. The Sidebar Is Too App-Like

From:

- `src/seeker_accounting/app/shell/sidebar.py`
- `src/seeker_accounting/app/shell/shell_models.py`

the sidebar currently includes:

- module accordion behavior
- favorites
- recents
- embedded search
- icon rail collapse

This adds flexibility, but weakens the feeling of a hard accounting console.

Sage's navigation is stronger because it is less expressive and more fixed.

That makes it easier to scan.

## 4. Cards Are Overused

From:

- `QFrame#PageCard`
- `QFrame#InfoCard`
- dashboard panel rules in `qss_builder.py`

Seeker wraps many things in rounded cards.

That works for a modern app, but compared to Sage it creates:

- too many isolated islands
- too much surface language
- weaker parent/child hierarchy

Sage tends to use framed sections and window panels, not "cards everywhere".

## 5. Document Entry Is Still Form-First

From:

- `src/seeker_accounting/modules/sales/ui/sales_invoice_dialog.py`
- `src/seeker_accounting/modules/purchases/ui/purchase_bill_dialog.py`
- `src/seeker_accounting/modules/sales/ui/sales_invoice_lines_grid.py`
- `src/seeker_accounting/modules/purchases/ui/purchase_bill_lines_grid.py`

the current dialogs are built as:

- header form card
- lines card
- totals card
- button row

This is clean, but it still reads like a stacked CRUD dialog.

Sage's equivalent screens read like specialized accounting workstations.

That difference is why Seeker still feels far behind even when individual widgets are fine.

## 6. Tables Are Too Gentle

From:

- `src/seeker_accounting/shared/ui/table_helpers.py`
- global `QTableView` rules in `qss_builder.py`

Seeker tables currently favor:

- rounded table containers
- hidden grid
- soft headers
- subtle hover

That makes them visually nice, but less authoritative.

Sage tables feel sharper because:

- headers are more assertive
- grid rhythm is clearer
- row density is more controlled
- action/status columns are more legible

## Visual Differences That Matter Most

## 1. Border Radius

Seeker token today:

- `medium = 12`
- `large = 16`

That is far too soft for the Sage-like workstation direction.

Recommendation:

- shell and table surfaces: `0-3px`
- form controls: `2-4px`
- only overlays and special chips should exceed that

## 2. Page Padding

Seeker currently uses generous page padding and many nested margins.

Recommendation:

- primary work surfaces should feel tighter
- reduce page padding
- reduce card margins
- increase alignment discipline instead of using white space to separate sections

## 3. Background Strategy

Seeker currently uses a more stylized blue-gray palette.

Recommendation:

- move toward neutral operational grays
- reserve green/blue accent for state, selection, and primary actions
- let tables and data become visually dominant

## 4. Panel Headers

Sage often uses clear panel headers or toolbar strips.

Seeker often uses simple titles inside cards.

Recommendation:

- introduce section header bars
- add stable toolbar strips above lists and grids
- make each work area visibly named and actionable

## 5. Dialog Framing

Our dialogs are missing a stronger internal skeleton.

Recommendation:

- toolbar row at the top
- document identity strip
- metadata block in aligned columns
- dominant editable lines grid
- docked totals summary
- pinned bottom action rail

## Design Principles Seeker Should Borrow

## 1. Replace "card UI" with "work surface UI"

That means:

- fewer rounded containers
- more framed panels
- more structural separators
- more fixed zones

## 2. Prefer fixed rails over floating convenience

For the shell:

- top system bar
- action ribbon
- left module rail
- center work area
- bottom status rail

This is stronger for accounting than a soft modern topbar.

## 3. Make tables and document grids the star

Accounting products live or die by:

- lists
- ledgers
- document lines
- totals
- statuses

These should be the most visually refined elements in the app.

## 4. Standardize a single document-entry template

Every transactional screen should share the same grammar:

- header strip
- document meta
- lines grid
- totals
- actions

Right now each one is "clean", but still too custom and too generic at the same time.

## 5. Increase visual consequence

Primary actions, statuses, selected modules, and totals should feel more intentional.

Not louder.

Just more decisive.

## Specific Problems to Fix in Seeker

## Shell

### Problem

The shell feels like a modern app shell, not an accounting workstation shell.

### Why

- rounded chips
- multiple small topbar widgets competing for attention
- sidebar behavior that favors flexibility over scan speed
- not enough operational zoning

### Fix

Rebuild shell into:

- slim menu bar
- ribbon/action strip
- flatter left navigation rail
- stronger page title/action strip inside the workspace
- persistent bottom status rail

## Dashboard

### Problem

The dashboard is decent, but still card-driven and visually "product" oriented.

### Why

- panel shapes are soft
- spacing is generous
- tables and numbers do not dominate enough

### Fix

Move toward:

- stronger sectional framing
- denser KPI layout
- clearer header strips
- tighter tables
- more operational widgets and fewer decorative containers

## Transaction Dialogs

### Problem

Sales and purchase documents are usable but not yet professional-grade in posture.

### Why

- stacked cards
- insufficient toolbar structure
- line grids feel embedded instead of central
- totals are present but not anchored as powerfully as they should be

### Fix

Adopt a document workstation layout:

- top command row
- metadata strip
- large grid center
- right or lower-right totals dock
- predictable Save/Close rail

## Tables

### Problem

The tables are too gentle and rounded for the domain.

### Why

- no grid
- soft headers
- rounded outer shell
- modest hierarchy between header, body, and status

### Fix

Move toward:

- crisper header bars
- clearer row separators
- reduced radius
- denser rows
- stronger numeric alignment
- explicit status rendering

## Recommended Redesign Direction

## Direction Name

**Operational Desktop**

This should become Seeker's new design direction.

Its characteristics:

- neutral shell
- dense but calm layout
- low-radius surfaces
- crisp borders
- stronger tables
- ribbon-like action patterns
- fixed document-entry grammar

## Not Recommended

Do not just "beautify" the current UI.

That will not close the gap.

If we only:

- tweak colors
- improve icons
- add gradients
- polish cards

the product will still feel structurally weaker than Sage.

The problem is mostly architectural.

## Concrete Refactor Targets

## 1. New Token Set

Revise:

- `src/seeker_accounting/shared/ui/styles/tokens.py`
- `src/seeker_accounting/shared/ui/styles/palette.py`

Needed changes:

- lower radii
- tighter spacing scale
- denser control sizing
- more neutral palette
- stronger header/table contrast

## 2. Rebuild QSS Around Panels, Not Cards

Revise:

- `src/seeker_accounting/shared/ui/styles/qss_builder.py`

Needed changes:

- reduce "soft card" styling
- add panel header styles
- sharpen table styling
- simplify shell surfaces

## 3. Replace the Current Topbar Pattern

Revise:

- `src/seeker_accounting/app/shell/topbar.py`
- `src/seeker_accounting/app/shell/main_window.py`

Needed changes:

- split system menu from action ribbon
- reduce chip clutter
- create context-aware action strip

## 4. Simplify the Sidebar

Revise:

- `src/seeker_accounting/app/shell/sidebar.py`
- `src/seeker_accounting/app/shell/shell_models.py`

Needed changes:

- more static navigation hierarchy
- flatter selected states
- less visual ornament
- better scan rhythm

## 5. Introduce a Standard Document Workspace Template

Build a reusable pattern for:

- sales invoices
- purchase bills
- treasury transactions
- receipts/payments
- payroll dialogs where applicable

This should replace the current ad-hoc stacked form/card approach.

## 6. Make One Screen the Benchmark

Do not refactor the whole product blindly.

Pick one benchmark screen first.

Best candidate:

- `Purchase Bill`

Why:

- close to the Sage purchase order screenshot
- contains all the hard UI problems
- metadata + line grid + totals + actions all exist in one place

If Purchase Bill becomes excellent, the pattern can spread.

## Proposed Execution Plan

## Phase 1: Visual Foundation

Deliver:

- new palette
- new spacing/radius tokens
- updated panel/table/button language

Goal:

make the app stop feeling soft

## Phase 2: Shell Refactor

Deliver:

- rebuilt top system bar
- action ribbon
- simplified left rail
- stronger status bar

Goal:

make navigation and action hierarchy feel intentional

## Phase 3: Document Template

Deliver:

- one reusable transactional workspace structure

Apply first to:

- Purchase Bill

Goal:

make one mission-critical screen feel decisively professional

## Phase 4: Lists and Tables

Deliver:

- denser tables
- stronger headers
- consistent status columns
- list action zones

Goal:

make the data views feel like accounting tools, not app screens

## Phase 5: Dashboard

Deliver:

- tighter dashboard
- stronger section headers
- more structured overview layout

Goal:

keep the dashboard aligned with the new desktop grammar

## Final Assessment

The user is right.

Seeker is still far from Sage in UI maturity.

But the gap is understandable and addressable.

The main issue is not that Seeker is ugly.

The main issue is that Seeker is still speaking the wrong visual language for a serious accounting workstation.

Sage speaks in:

- rails
- grids
- ribbons
- panels
- status
- density

Seeker currently speaks more in:

- cards
- chips
- soft containers
- generic modern app patterns

If we shift Seeker from **soft SaaS shell** to **operational desktop shell**, the product can move much closer to the level of precision the benchmark is communicating.
