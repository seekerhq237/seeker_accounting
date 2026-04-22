# Ambient Intelligence Plan

## Goal

Make Seeker feel like it has a quiet brain.

The feature should:

- surface faint, ignorable thoughts tied to the user's current context
- never block entry, save, posting, or navigation
- move with the user across modules and forms
- be draggable anywhere on screen
- be easy to turn off completely
- stay explainable and trustworthy

This is not a chat assistant. It is an ambient guidance layer.

## Product Principles

1. Stay out of the way.
   The system should wait for a pause, then whisper. It must not steal focus or interrupt typing.

2. Be local to context.
   Thoughts should depend on the exact place the user is in: page, dialog, entity, draft state, active company, fiscal period, and nearby deadlines.

3. Be explainable.
   Every thought should come from visible product truth: rules, recent activity, document state, trends, or deadlines.

4. Be dismissible.
   Users must be able to drag it, snooze it, mute a thought type, or turn the entire system off.

5. Be useful before it is "AI".
   Rule-based intelligence should ship first. AI can improve phrasing, ranking, and summarization later, but not truth.

## UX Shape

### Core Surface

Introduce a small floating widget called the **Thought Chip**:

- faint background and soft border
- one short sentence at a time
- subtle tone styles: `hint`, `caution`, `projection`
- optional expand affordance for more detail
- appears after a short idle pause
- never modal
- never blocks clicks beneath except inside its own body

Example copy:

- "VAT on this draft is higher than this customer's recent pattern."
- "This payroll run will create remittance work due by the 15th."
- "Recoverable VAT may be risky here because supplier tax details are incomplete."
- "Cash would fall below recent payroll outflow if this payment posts today."

### Expanded State

When expanded, the chip becomes a small **Thought Panel** with:

- the thought sentence
- one-line explanation
- confidence label such as `Likely`, `Watch`, `High confidence`
- actions:
  - `Dismiss`
  - `Snooze`
  - `Why`
  - `Turn Off`

### Dragging

The chip must be draggable.

Recommended behavior:

- default position: bottom-right
- user can drag by grabbing the chip body or a subtle drag handle
- free movement within the shell viewport
- clamp to visible bounds
- snap softly to nearby edges on release
- persist position between sessions

Important implementation detail:

- persist a normalized position rather than raw pixels
- example: `anchor = bottom_right`, `offset_x_ratio = -0.04`, `offset_y_ratio = -0.06`
- this keeps placement stable across window sizes and monitor resolutions

### Turning It Off

Users should have three levels of control:

1. **Quick hide**
   Dismiss the current thought only.

2. **Snooze**
   Hide thoughts for a period such as `1 hour`, `today`, or `this session`.

3. **Master off switch**
   Disable ambient thoughts entirely until turned back on.

Best control surfaces:

- inside the thought panel: `Turn Off Ambient Thoughts`
- inside the profile menu in the top bar
- via command palette action: `Toggle Ambient Thoughts`

This should be a **user preference**, not a company preference.

## Where It Fits in Seeker

The cleanest shell integration point is `WorkspaceHost`, which already:

- owns page materialization
- tracks current navigation context
- installs the floating help button on feature pages

Relevant current patterns:

- `src/seeker_accounting/app/shell/workspace_host.py`
- `src/seeker_accounting/shared/ui/help_button.py`
- `src/seeker_accounting/shared/ui/help_overlay.py`
- `src/seeker_accounting/shared/services/notification_center.py`
- `src/seeker_accounting/modules/reporting/services/insight_rules_service.py`
- `src/seeker_accounting/modules/payroll/services/payroll_output_warning_service.py`
- `src/seeker_accounting/shared/services/sidebar_preferences_service.py`

These give us:

- shell-level floating UI patterns
- non-blocking explainable intelligence patterns
- lightweight local per-user preference storage

## Proposed Architecture

### 1. Preference Store

Add a new local user preference service:

- `src/seeker_accounting/shared/services/ambient_thought_preferences_service.py`

Responsibility:

- persist `enabled`
- persist `snoozed_until`
- persist widget position
- persist muted thought codes
- persist optional intensity mode such as `minimal` or `standard`

Recommended storage:

- JSON in the same local app-data area used by `SidebarPreferencesService`

Suggested schema:

```json
{
  "enabled": true,
  "snoozed_until": null,
  "position": {
    "anchor": "bottom_right",
    "x_ratio": 0.92,
    "y_ratio": 0.88
  },
  "muted_codes": [],
  "mode": "minimal"
}
```

### 2. Thought DTOs

Add small DTOs for thought generation and rendering:

- `AmbientThoughtContextDTO`
- `AmbientThoughtDTO`

Suggested `AmbientThoughtDTO` fields:

- `thought_code`
- `tone`
- `summary`
- `detail`
- `confidence_score`
- `importance_score`
- `source_kind`
- `nav_id`
- `entity_type`
- `entity_id`
- `actions`
- `why_items`
- `expires_at`

### 3. Context Collector

Add:

- `src/seeker_accounting/shared/services/ambient_thought_context_service.py`

Responsibility:

- assemble the current context from shell and page state
- read:
  - current `nav_id`
  - current navigation context
  - active company
  - current fiscal period
  - selected record or draft id when available
  - page-specific draft values through an optional page contract

Suggested page contract:

```python
def get_ambient_context(self) -> dict[str, object]:
    ...
```

Pages and dialogs that have richer local state can implement this without forcing every page to change at once.

### 4. Thought Service

Add:

- `src/seeker_accounting/shared/services/ambient_thought_service.py`

Responsibility:

- orchestrate all thought providers
- gather thoughts for the current context
- filter muted or stale thoughts
- rank results
- return the best current thought

Public API:

- `get_best_thought(context) -> AmbientThoughtDTO | None`
- `get_thoughts(context) -> tuple[AmbientThoughtDTO, ...]`

### 5. Thought Providers

Use a provider pattern by domain.

Suggested providers:

- `sales_thought_provider.py`
- `purchases_thought_provider.py`
- `payroll_thought_provider.py`
- `tax_thought_provider.py`
- `treasury_thought_provider.py`
- `master_data_thought_provider.py`
- `reporting_thought_provider.py`

Each provider should be rule-based and explainable.

Examples:

#### Sales

- unusual tax amount versus customer history
- invoice due date shorter than customer norm
- draft margin unusually low
- customer has overdue balance and a new invoice is being raised

#### Purchases

- supplier bill lacks tax code on a line
- recoverable VAT risk because tax details are incomplete
- bill date falls in a locked or closing period
- duplicate amount and supplier pattern detected near prior bill

#### Payroll

- remittance due soon after posting
- employee compensation profile missing or nearing end date
- payroll run uses provisional statutory pack values
- payroll outflow trend is rising faster than prior months

#### Tax

- tax code effective date starts next period
- selected tax code appears inconsistent with document type
- company preference is tax-inclusive but document lines are being entered as exclusive
- upcoming VAT filing or DSF action is approaching

#### Treasury

- payment reduces cash below recent payroll or supplier run-rate
- transfer timing may leave the source account short
- unreconciled statement backlog is rising

### 6. Overlay Widget

Add:

- `src/seeker_accounting/shared/ui/ambient_thought_overlay.py`

Responsibility:

- render the floating chip/panel
- fade in after idle delay
- support dragging
- support collapse/expand
- support dismiss, snooze, and off actions

Suggested behavior:

- child of shell root, same broad parent strategy as help overlay
- translucent, low-contrast styling
- `WA_ShowWithoutActivating` where appropriate
- no keyboard focus capture except for explicit button clicks

### 7. Shell Host

Integrate with `WorkspaceHost`:

- instantiate one ambient overlay for the shell
- refresh when:
  - navigation changes
  - navigation context changes
  - active company changes
  - relevant page emits a `ambient_context_changed` signal

Debounce refresh to avoid churn while the user is typing.

Recommended debounce:

- `500ms` after last context update

### 8. Settings Entry Points

Add control surfaces in:

- `src/seeker_accounting/app/shell/user_profile_menu.py`
- `src/seeker_accounting/app/shell/command_palette_providers.py`

Recommended additions:

- profile menu row: `Ambient Thoughts: On/Off`
- command palette action: `Toggle Ambient Thoughts`
- command palette action: `Snooze Ambient Thoughts`

Optional later:

- a dedicated user preferences dialog

## Interaction Rules

### When to Show

Show a thought only when:

- the user has been idle briefly
- no modal dialog is blocking the page unless the thought belongs to that dialog
- the overlay is enabled and not snoozed
- the best thought clears a minimum relevance threshold

### When Not to Show

Suppress thoughts when:

- the user is actively typing fast
- a dropdown, date picker, or critical modal is open
- the current page is in a destructive confirmation flow
- the same thought was just ignored repeatedly
- the result is low-confidence and non-actionable

### Frequency Rules

- one visible thought at a time
- do not rotate thoughts too aggressively
- if unchanged, keep the current thought stable
- refresh only when context materially changes

This prevents the "haunted interface" effect.

## Ranking Model

Use a simple deterministic ranking formula first:

`final_score = relevance + urgency + confidence + novelty - annoyance_penalty`

Inputs:

- `relevance`: how tightly tied the thought is to the current page or entity
- `urgency`: deadline or risk proximity
- `confidence`: strength of the rule evidence
- `novelty`: not recently shown
- `annoyance_penalty`: repeated ignores or user-muted categories

Keep this explainable and testable.

## Explainability

Every thought should be able to answer "Why?" with short bullets like:

- "Customer overdue balance exceeds 45 days."
- "This invoice tax amount is 28% above the customer's recent average."
- "The active fiscal period is closing."

This is essential if the system is to feel intelligent rather than random.

## AI Strategy

### Phase 1: No LLM required

Ship with rules, trend calculations, deadlines, and heuristics only.

Benefits:

- predictable
- fast
- offline-capable
- easy to test
- safe for accounting workflows

### Phase 2: Optional AI Assist

If we later add AI, use it only for:

- phrasing the thought more naturally
- choosing between similar candidate thoughts
- producing a short forecast sentence

Do not let AI invent accounting facts or compliance logic.

Suggested contract:

- providers produce candidate facts
- AI rewrites or summarizes only
- final thought still includes structured evidence from the providers

## Proposed File Plan

### New files

- `src/seeker_accounting/shared/services/ambient_thought_preferences_service.py`
- `src/seeker_accounting/shared/services/ambient_thought_context_service.py`
- `src/seeker_accounting/shared/services/ambient_thought_service.py`
- `src/seeker_accounting/shared/dto/ambient_thought_dto.py`
- `src/seeker_accounting/shared/ui/ambient_thought_overlay.py`
- `src/seeker_accounting/shared/ui/ambient_thought_styles.py` if style helpers are needed
- `src/seeker_accounting/modules/sales/services/sales_thought_provider.py`
- `src/seeker_accounting/modules/purchases/services/purchases_thought_provider.py`
- `src/seeker_accounting/modules/payroll/services/payroll_thought_provider.py`
- `src/seeker_accounting/modules/accounting/reference_data/services/tax_thought_provider.py`
- `src/seeker_accounting/modules/treasury/services/treasury_thought_provider.py`

### Existing files to update

- `src/seeker_accounting/app/dependency/service_registry.py`
- `src/seeker_accounting/app/dependency/factories.py`
- `src/seeker_accounting/app/shell/workspace_host.py`
- `src/seeker_accounting/app/shell/user_profile_menu.py`
- `src/seeker_accounting/app/shell/topbar.py` if the profile-menu wiring needs new signals
- `src/seeker_accounting/app/shell/command_palette_providers.py`

### Optional page changes

High-value pages can implement:

- `get_ambient_context()`
- `ambient_context_changed` signal

Start with:

- Sales invoice dialogs/pages
- Purchase bill dialogs/pages
- Payroll workspaces
- Tax code setup page
- Treasury transaction/payment dialogs

## Rollout Phases

### Phase 0: Shell Foundation

Deliver:

- preference store
- overlay widget
- drag behavior
- master on/off toggle
- snooze
- command palette/profile menu wiring
- shell integration and debounce

No accounting intelligence yet except a simple demo thought.

Success criteria:

- draggable chip works
- preference persists
- user can fully disable it

### Phase 1: Context Plumbing

Deliver:

- context collector
- page contract for rich context
- first context change signals from key screens

Target screens:

- sales invoices
- purchase bills
- payroll calculation

Success criteria:

- overlay updates when the user changes meaningful document state

### Phase 2: Rule-Based Thoughts

Deliver first provider set:

- sales
- purchases
- payroll
- tax
- treasury

Success criteria:

- thoughts are clearly relevant
- false positives stay low
- no blocking behavior

### Phase 3: Explainability and Controls

Deliver:

- `Why` panel
- mute by thought code/category
- ignore tracking
- annoyance penalty

Success criteria:

- users can understand and tame the system

### Phase 4: Forecasting

Deliver:

- trend-based projection thoughts
- deadline proximity thoughts
- cash impact projection thoughts

Examples:

- "At the current pace, unpaid supplier balances may exceed last month's level by period-end."
- "Posting this run now likely creates remittance work due within 5 days."

### Phase 5: Optional AI Layer

Deliver only if needed:

- natural phrasing
- ranking refinement
- summary quality improvements

## Testing Strategy

### Unit Tests

Test:

- preference read/write
- normalized position persistence
- clamp and snap calculations
- provider scoring
- snooze and mute logic
- ranking stability

### UI Tests

Test:

- overlay appears after debounce
- overlay remains non-blocking
- drag persists across relaunch
- off toggle hides overlay immediately
- resize preserves visible placement

### Acceptance Tests

Scenarios:

- user drags chip to top-left and restarts app
- user turns off ambient thoughts in profile menu
- user snoozes for session
- user edits a sales invoice and sees a relevant caution
- user opens payroll and gets a deadline projection

## Risks and Guardrails

### Risk: Noise

Guardrail:

- strict thresholds
- one thought at a time
- ignore tracking

### Risk: Wrong advice

Guardrail:

- rule-based evidence first
- visible `Why`
- confidence scoring

### Risk: UI clutter

Guardrail:

- low-contrast chip
- draggable
- easy off

### Risk: Cross-page inconsistency

Guardrail:

- shared context DTO
- provider contract
- `WorkspaceHost` owns shell-level behavior

## Recommended First Slice

If we want the strongest first delivery with the least risk, build this sequence:

1. `AmbientThoughtPreferencesService`
2. `AmbientThoughtOverlay`
3. shell integration in `WorkspaceHost`
4. profile menu and command palette toggle
5. one simple provider for payroll deadlines
6. one simple provider for sales invoice tax anomaly

That will let the team feel the product idea quickly without overcommitting to a large intelligence layer on day one.

## Recommendation

Treat this feature as **Ambient Intelligence**, not "AI assistant".

That framing keeps the product elegant:

- it whispers instead of interrupts
- it is movable
- it is optional
- it stays grounded in Seeker's accounting truth

Once the shell foundation is in place, the intelligence can grow module by module without changing the overall experience.
