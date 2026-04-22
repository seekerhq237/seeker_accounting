# Seeker Accounting — UI Style Guide

**Direction: Operational Desktop.** This document is the contract for every UI surface in Seeker. It is not descriptive — it is prescriptive. Deviations require an explicit decision recorded in the plan.

Reference benchmark: Sage 50. Character goal: serious, dense, flat, neutral, precise. Seeker must read as *operational tooling*, not *marketing dashboard*.

---

## 1. Design principles

1. **Flat framing over cards.** Panels are flat rectangles with a hairline border. Rounded "card" chrome is forbidden on primary work surfaces (registers, document workstations, dashboards).
2. **Density over whitespace.** Padding is tight. Tables are dense. Labels are small. The workspace is a tool, not a magazine.
3. **Neutral grays, single accent.** The default UI is monochrome. Color is reserved for state (success/warning/danger/info) and for the single restrained accent on interactive elements.
4. **Content over chrome.** The user is looking at the data. Shell chrome exists to route and command, then gets out of the way.
5. **Every surface has a frame and a header.** Content does not float. Panels always declare themselves.
6. **Consistency over local cleverness.** If the grammar doesn't cover it, revise the grammar — do not invent a one-off.

---

## 2. Radius scale

Radii are **aggressively low**. Nothing on a primary work surface exceeds 4 px.

| Token | Value | Use |
|---|---|---|
| `radius.small` | **2 px** | Inputs, buttons, chips, tabs, table cells |
| `radius.medium` | **4 px** | Panels, toolbars, cards, dialogs |
| `radius.large` | **6 px** | Overlay menus, popovers |
| `radius.xlarge` | **8 px** | Modal-only decorative surfaces (splash, first-run) |

**Forbidden**: hardcoded radii > 6 px on work surfaces. Existing hardcoded 12 px / 15 px / 16 px / 24 px / 36 px values in `qss_builder.py` are exceptions tied to entry-point screens (splash, get-started hero, shortcut chip) and remain allowed *only* there.

---

## 3. Spacing scale

| Token | Value | Use |
|---|---|---|
| `spacing.page_padding` | 16 px | Outer workspace padding |
| `spacing.section_gap` | 12 px | Gap between major panels |
| `spacing.compact_gap` | 6 px | Gap within a panel |
| `spacing.control_gap` | 8 px | Gap between controls in a row |
| `spacing.sidebar_padding` | 10 px | Sidebar internal padding |

Keep numbers on an 2-px rhythm. No 7, 11, 13, 17, 19. Use 2, 4, 6, 8, 10, 12, 14, 16, 20, 24.

---

## 4. Size scale

| Token | Value | Use |
|---|---|---|
| `sizes.sidebar_width` | 200 px | Expanded rail |
| `sizes.sidebar_collapsed_width` | 56 px | Icon-only rail |
| `sizes.topbar_height` | 44 px | Command band (reduced from 56) |
| `sizes.topbar_control_height` | 28 px | Command band controls |
| `sizes.control_height` | 24 px | Inputs/buttons in forms |
| `sizes.button_height` | 24 px | Action buttons |
| `sizes.row_height` | 26 px | Table rows (compact) |
| `sizes.row_height_dense` | **22 px** | Table rows (dense — used in registers) |
| `sizes.panel_header_height` | **28 px** | Panel header strip |
| `sizes.toolbar_strip_height` | **34 px** | Local toolbar strip within a panel |
| `sizes.command_band_height` | 44 px | Shell command band (= topbar) |
| `sizes.status_rail_height` | 24 px | Bottom status rail |

---

## 5. Typography

| Token | Size | Weight | Use |
|---|---|---|---|
| `size_app_title` | 20 | 600 | Window title only |
| `size_section_title` | 14 | 600 | Panel headers |
| `size_card_title` | 13 | 600 | Group titles inside panels |
| `size_body` | 12 | 400 | Default UI text |
| `size_small` | 11 | 400 | Secondary meta |
| `size_dense` | 11 | 400 | Dense table cells |
| `size_caption` | 10 | 500 | Chips, pills, status tags |

Font family: `Segoe UI` (Windows). Numeric columns should prefer tabular figures where available — `font-feature-settings: "tnum"` is not reliably honoured in Qt QSS, so alignment is the enforcer (see §9).

---

## 6. Palette (light)

Neutral operational grays. The app_background is slightly cooler than the workspace surface so the workspace visibly sits *inside* the shell.

| Role | Hex | Intent |
|---|---|---|
| `app_background` | `#EEF1F5` | Shell chrome background |
| `workspace_surface` | `#FFFFFF` | Content panels |
| `secondary_surface` | `#F4F6FA` | Alternating/meta surfaces |
| `raised_surface` | `#FFFFFF` | Dialogs, popovers |
| `sidebar_surface` | `#E8ECF2` | Sidebar rail |
| `sidebar_hover` | `#DCE2EB` | Sidebar hover |
| `topbar_surface` | `#F4F6FA` | Command band |
| `border_default` | `#D4DAE3` | Hairline panel border |
| `border_strong` | `#B6BFCC` | Panel header separator, focused input |
| `divider_subtle` | `#E4E8EE` | In-panel separators |
| `text_primary` | `#1A2230` | Body |
| `text_secondary` | `#4E5866` | Secondary labels |
| `text_muted` | `#7A8392` | Meta / placeholders |
| `accent` | `#1F5BD8` | Primary action, link, focus ring |
| `accent_hover` | `#1A4EBA` | Primary action hover |
| `accent_soft` | `#EEF3FE` | Accent tint background (light fills) |
| `accent_soft_strong` | `#D4E1FB` | Selected rows, active tab underline |
| `accent_text` | `#FFFFFF` | Text on accent fills |
| `success` | `#1E7A5A` | Posted / approved |
| `warning` | `#9A6A17` | Draft / needs attention |
| `danger` | `#B42E2E` | Void / overdue / destructive |
| `info` | `#1F5BD8` | Informational chips (= accent) |
| `table_header` | `#E8ECF2` | Table header background |
| `table_hover` | `#F2F5F9` | Row hover |
| `selected_fill` | `#D9E3F7` | Selected row |
| `selected_text` | `#11223B` | Selected row text |
| `input_surface` | `#FFFFFF` | Input background |
| `input_border` | `#C3CBD6` | Input border |
| `input_focus` | `#1F5BD8` | Input focus ring |
| `disabled_surface` | `#EAEDF2` | Disabled input |
| `disabled_text` | `#8A93A2` | Disabled text |

## 7. Palette (dark)

Parity with light. No blue cast on the chrome.

| Role | Hex |
|---|---|
| `app_background` | `#0D1219` |
| `workspace_surface` | `#161C26` |
| `secondary_surface` | `#141A24` |
| `raised_surface` | `#1A202B` |
| `sidebar_surface` | `#0F141D` |
| `sidebar_hover` | `#1A2131` |
| `topbar_surface` | `#141A24` |
| `border_default` | `#2A3241` |
| `border_strong` | `#3A4354` |
| `divider_subtle` | `#1E2531` |
| `text_primary` | `#ECEFF5` |
| `text_secondary` | `#BDC5D2` |
| `text_muted` | `#8B95A5` |
| `accent` | `#5B8BEF` |
| `accent_hover` | `#7099F0` |
| `accent_soft` | `#192337` |
| `accent_soft_strong` | `#22314E` |
| `accent_text` | `#F5F7FB` |
| `success` | `#34C58A` |
| `warning` | `#E8B764` |
| `danger` | `#F07070` |
| `info` | `#5B8BEF` |
| `table_header` | `#1A2131` |
| `table_hover` | `#1B2433` |
| `selected_fill` | `#24344F` |
| `selected_text` | `#F5F7FB` |
| `input_surface` | `#161C26` |
| `input_border` | `#32394A` |
| `input_focus` | `#5B8BEF` |
| `disabled_surface` | `#171E2A` |
| `disabled_text` | `#6E7789` |

---

## 8. Surface primitives (QSS object names)

These are the **only** sanctioned primary-surface primitives. New features must use these.

| Object name | Role |
|---|---|
| `QFrame#Panel` | Flat framed container. Hairline `border_default`, `radius.medium`, background `workspace_surface`. |
| `QFrame#PanelHeader` | Header strip at top of a Panel. `panel_header_height`, background `secondary_surface`, bottom border `border_default`. Contains `QLabel#PanelTitle` + optional right-aligned actions. |
| `QFrame#ToolbarStrip` | Local toolbar inside a Panel. `toolbar_strip_height`, background `secondary_surface`, bottom border hairline. |
| `QFrame#CommandBand` | Shell command band at top of window. `command_band_height`, background `topbar_surface`, bottom border `border_default`. |
| `QFrame#StatusRail` | Bottom status rail. `status_rail_height`, background `secondary_surface`, top border hairline. |
| `QFrame#DocumentWorkspace` | Document-entry container. Owns the five zones (see §12). |
| `QFrame#MetaStrip` | Document identity/meta strip. Compact, hairline bottom. |
| `QFrame#TotalsDock` | Right-docked totals panel. Hairline left border. |

**Legacy compatibility:** `QFrame#PageCard`, `QFrame#InfoCard`, `QFrame#PageToolbar`, `DashboardPanel`, `MoneyCard` remain in the QSS but now inherit the flat framing. They are kept only for migration continuity. All new work uses the primitives above.

---

## 9. Tables

Tables are the heart of Seeker. They must look authoritative.

- **Header**: background `table_header`, bottom border 1 px `border_strong`, weight 600, text `text_secondary`, size 11. Left-padded 8 px.
- **Cells**: 22 px row height (dense) or 26 px (compact). Font size 12. No per-row borders — a single hairline `divider_subtle` between rows is optional (off by default to match Sage).
- **Grid lines**: off by default. Use column separators only when density requires them.
- **Selection**: full-row fill `selected_fill`, text `selected_text`.
- **Hover**: `table_hover`.
- **Numeric columns**: right-aligned, monospaced if the data is reference (codes, IDs); proportional otherwise. Currency shows separators and 2 decimals. Negatives in `danger` color, never parentheses.
- **Status**: never plain text. Always a `StatusChip` (§11).
- **No zebra striping** by default. If a report table opts in, use `secondary_surface` for alternate rows.

Adopt `configure_dense_table(table)` for register tables; existing `configure_compact_table` stays for document-line grids.

---

## 10. Forms and inputs

- Inputs are **24 px tall**. `QLineEdit`, `QComboBox`, `QDateEdit`, `QSpinBox` share the same height.
- Border: 1 px `input_border`, radius `small` (2 px), background `input_surface`.
- Focus ring: 1 px `input_focus` (no glow).
- Labels sit **above** inputs in form cards; labels sit **left** in meta strips.
- Required fields: no asterisk noise — validation errors surface inline (red outline + helper text) only on submit attempt.
- Number inputs right-align.
- Placeholder text uses `text_muted`.

---

## 11. Status chips

Flat. Hairline. Weight 500. Size 10. Radius 2 px. Text uppercase.

| State | Text color | Background |
|---|---|---|
| `draft` | `warning` | `warning @ 12% alpha` (painted as solid tint) |
| `posted` / `approved` / `paid` | `success` | `success @ 12% alpha` |
| `partial` | `info` | `info @ 12% alpha` |
| `overdue` / `void` | `danger` | `danger @ 12% alpha` |
| `locked` / `closed` | `text_muted` | `divider_subtle` |
| `pending` | `text_secondary` | `secondary_surface` |

Chips must never be the only signal — tables also sort and filter by status code.

---

## 12. Document workstation template

Every document-entry screen (Sales Invoice, Purchase Bill, Credit Note, Journal Entry, Receipt, Payment, Quote, Order, Payslip) follows this **locked** template:

```
┌─────────────────────────────────────────────────────────────┐
│ (A) Command row — Save / Post / Void / Print / Export / ... │
├─────────────────────────────────────────────────────────────┤
│ (B) Identity strip — Doc type · No. · Status · Dates · Party│
├─────────────────────────────────────────────────────────────┤
│                                              ┌────────────┐ │
│ (C) Meta block                               │ (E) Totals │ │
│     2-column aligned grid                    │    Dock    │ │
│                                              │            │ │
│ (D) Lines grid — dominant, stretch           │  Subtotal  │ │
│                                              │  Tax       │ │
│                                              │  Total     │ │
│                                              │            │ │
├─────────────────────────────────────────────────────────────┤
│ (F) Bottom action rail — Save / Cancel / Close              │
└─────────────────────────────────────────────────────────────┘
```

Rules:
- Zone (A) lives either in the shell command band (when the doc opens as a workspace route) or as a local `ToolbarStrip` (when the doc opens in a dialog).
- Zone (B) is one line tall. Meta is tab-separated label-value pairs.
- Zone (C) uses a 2-column `QFormLayout` with fixed label column width.
- Zone (D) stretches vertically and horizontally. It is always the visually dominant element.
- Zone (E) is right-docked at **220 px wide**, flat, hairline left border.
- Zone (F) is a bottom rail only in dialog mode.

Benchmark implementation: **Purchase Bill** (Phase 3).

---

## 13. Register template

Every list page (Customers, Suppliers, Sales Invoices, Purchase Bills, Journals, Chart of Accounts, Items) uses this layout:

```
┌─────────────────────────────────────────────────────────────┐
│ (A) Toolbar strip — Search · Filters · Status · Count       │
├─────────────────────────────────────────────────────────────┤
│ (B) Action band — New · Edit · Post · Cancel · Export       │
├─────────────────────────────────────────────────────────────┤
│ (C) Dense table (stretch)                                    │
│                                                              │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│ (D) Preview pane (optional, bottom-docked, hideable)        │
└─────────────────────────────────────────────────────────────┘
```

- The register fills the workspace. No outer `PageCard` wrapping.
- Zone (A) is a single `ToolbarStrip`.
- Zone (B) is flat, hairline top border, 36 px tall, left-aligned buttons.
- Zone (C) is a dense table (§9).

---

## 14. Shell structure

```
┌──────────────────────────────────────────────────────────────┐
│ Menu bar (native-style: File · Edit · View · Records · ...)  │  24 px
├───────┬──────────────────────────────────────────────────────┤
│       │ Command band (context actions)                       │  44 px
│ Side  ├──────────────────────────────────────────────────────┤
│ bar   │                                                      │
│       │                                                      │
│ 200px │ Workspace (register | document | dashboard)          │
│       │                                                      │
│       │                                                      │
│       ├──────────────────────────────────────────────────────┤
│       │ Status rail (company · period · user · db · version) │  24 px
└───────┴──────────────────────────────────────────────────────┘
```

- Menu bar: in-window (not system-native), File/Edit/View/Records/Reports/Tools/Help.
- Command band: three zones left→right — **Records** (New, Find, Refresh), **Document** (active-page actions), **Context** (company, period, license, notifications, theme, profile).
- Sidebar: flat rail, module accordion, no embedded search/favorites/recents. Single selected-state accent.
- Status rail: left `Company · Period · User`, center background-task indicator, right `DB backend · Version`.

---

## 15. Iconography

- Icon set: **Lucide** via `shared/ui/icon_provider.py`. No mixing with Unicode glyphs.
- Sizes: **16 px** in command band and toolbars; **14 px** in registers and action bands; **12 px** in inline chips.
- Stroke weight: default Lucide. Icons are monochrome, inherit `text_secondary`, go to `accent` on selected state.
- Icons in buttons sit left of the label with a 6 px gap.

---

## 16. Motion

Seeker is not animated software. Transitions are sub-perceptual (≤ 120 ms ease) or absent. No sliding panels. No skeleton shimmers. The busy state is a small spinner in the status rail.

---

## 17. Light / dark parity rules

- The two themes must feel equally serious. Dark is not a sexed-up night mode — it is the same grammar on dark chrome.
- Never swap radii, spacing, or typography between themes.
- No glow, no gradient fills except where the palette tokens explicitly include a tint (`accent_soft`).

---

## 18. What is forbidden

1. Hardcoded hex colors in widget code. Always use palette or QSS.
2. Radii > 6 px on primary work surfaces.
3. Rounded card drop shadows.
4. Gradient backgrounds on work surfaces.
5. Unicode glyph icons (`≡`, `v`, `?`) — use Lucide.
6. Plain-text status columns — use `StatusChip`.
7. `QMessageBox` for non-blocking feedback — use the notifier.
8. Inline `setStyleSheet` in feature code — extend the QSS builder.
9. Wrapping a register in `PageCard`. Registers *are* the surface.
10. Per-page custom toolbar layouts. Use `ToolbarStrip` + action band.

---

## 19. How to add a new surface

1. Identify which template fits: register, document workstation, dashboard, entity detail, or dialog.
2. Reach for the primitive by object name (§8).
3. If a new primitive is genuinely needed, propose it — update this document first, then the QSS builder, then the feature.
4. Validate offscreen in both themes.
5. Capture a before/after screenshot for the phase.

---

## 20. Versioning

This document is versioned with the plan. Every phase commits or amends a section. When a section changes, update the date below and note the phase.

- **v1.0** — Phase 0, initial lock.
