# Ribbon Context Plan — Seeker Accounting

**Status:** Working document — updated as implementation progresses  
**Scope:** All nav_id contexts + child window contexts in the ribbon system  
**Purpose:** Track every surface, its command definition, enablement rules, and implementation status

---

## 1. Implementation Status — Master Table

| nav_id / context            | Surface key              | Surface exists | Page wired | Priority |
|-----------------------------|--------------------------|:--------------:|:----------:|:--------:|
| `journals`                  | `journals`               | ✅              | ✅          | Done     |
| `sales_invoices`            | `sales_invoices`         | ✅              | ✅          | Done     |
| `customers`                 | `customers`              | ✅              | ✅          | Done     |
| `suppliers`                 | `suppliers`              | ✅              | ✅          | Done     |
| `purchase_bills`            | `purchase_bills`         | ✅              | ✅          | Done     |
| `chart_of_accounts`         | `chart_of_accounts`      | ✅              | ✅          | Done     |
| `treasury_transactions`     | `treasury_transactions`  | ✅              | ✅          | Done     |
| `treasury_transfers`        | `treasury_transfers`     | ✅              | ✅          | Done     |
| `child:journal_entry`       | `child:journal_entry`    | ✅              | ✅          | Done     |
| `items`                     | `items`                  | ✅              | ⬜          | Phase 3A |
| `sales_orders`              | `sales_orders`           | ⚠️ partial      | ⬜          | Phase 3A |
| `customer_quotes`           | `customer_quotes`        | ⚠️ partial      | ⬜          | Phase 3A |
| `sales_credit_notes`        | `sales_credit_notes`     | ✅              | ⬜          | Phase 3A |
| `customer_receipts`         | `customer_receipts`      | ✅              | ⬜          | Phase 3A |
| `purchase_orders`           | `purchase_orders`        | ⚠️ partial      | ⬜          | Phase 3A |
| `purchase_credit_notes`     | `purchase_credit_notes`  | ✅              | ⬜          | Phase 3A |
| `supplier_payments`         | `supplier_payments`      | ✅              | ⬜          | Phase 3A |
| `companies`                 | —                        | ⬜              | ⬜          | Phase 3B |
| `payment_terms`             | —                        | ⬜              | ⬜          | Phase 3B |
| `tax_codes`                 | —                        | ⬜              | ⬜          | Phase 3B |
| `document_sequences`        | —                        | ⬜              | ⬜          | Phase 3B |
| `account_role_mappings`     | —                        | ⬜              | ⬜          | Phase 3B |
| `fiscal_periods`            | —                        | ⬜              | ⬜          | Phase 3B |
| `financial_accounts`        | —                        | ⬜              | ⬜          | Phase 3B |
| `statement_lines`           | —                        | ⬜              | ⬜          | Phase 4  |
| `bank_reconciliation`       | —                        | ⬜              | ⬜          | Phase 4  |
| `uom_categories`            | —                        | ⬜              | ⬜          | Phase 4  |
| `units_of_measure`          | —                        | ⬜              | ⬜          | Phase 4  |
| `item_categories`           | —                        | ⬜              | ⬜          | Phase 4  |
| `inventory_locations`       | —                        | ⬜              | ⬜          | Phase 4  |
| `inventory_documents`       | —                        | ⬜              | ⬜          | Phase 4  |
| `stock_position`            | —                        | ⬜              | ⬜          | Phase 5  |
| `asset_categories`          | —                        | ⬜              | ⬜          | Phase 4  |
| `assets`                    | —                        | ⬜              | ⬜          | Phase 4  |
| `depreciation_runs`         | —                        | ⬜              | ⬜          | Phase 4  |
| `contracts`                 | —                        | ⬜              | ⬜          | Phase 4  |
| `projects`                  | —                        | ⬜              | ⬜          | Phase 4  |
| `payroll_setup`             | —                        | ⬜              | ⬜          | Phase 5  |
| `payroll_calculation`       | —                        | ⬜              | ⬜          | Phase 5  |
| `payroll_accounting`        | —                        | ⬜              | ⬜          | Phase 5  |
| `payroll_operations`        | —                        | ⬜              | ⬜          | Phase 5  |
| `administration`            | —                        | ⬜              | ⬜          | Phase 4  |
| `roles`                     | —                        | ⬜              | ⬜          | Phase 4  |
| `organisation_settings`     | —                        | ⬜              | ⬜          | Phase 4  |
| `backup_restore`            | —                        | ⬜              | ⬜          | Phase 5  |
| `reports`                   | —                        | N/A            | N/A        | Deferred |
| `project_variance_analysis` | —                        | N/A            | N/A        | Deferred |
| `contract_summary`          | —                        | N/A            | N/A        | Deferred |
| `audit_log`                 | —                        | N/A            | N/A        | Deferred |
| `dashboard`                 | —                        | N/A            | N/A        | N/A      |
| `customer_detail`           | —                        | N/A            | N/A        | Deferred |
| `supplier_detail`           | —                        | N/A            | N/A        | Deferred |
| `account_detail`            | —                        | N/A            | N/A        | Deferred |
| `item_detail`               | —                        | N/A            | N/A        | Deferred |
| `sales_invoice_detail`      | —                        | ⬜              | ⬜          | Deferred |
| `purchase_bill_detail`      | —                        | ⬜              | ⬜          | Deferred |

**Legend:** ✅ complete · ⚠️ partial (surface exists but needs extra buttons) · ⬜ pending · N/A not applicable

---

## 2. Phase 2 — Already Complete

These pages are fully wired as `IRibbonHost` with the action_band hidden. No further work needed.

### 2.1 Toolbar style note

All Phase 2 pages use `RegisterPage.action_band` (the standard `_populate_action_band` pattern).  
After `_populate_action_band(self._register)`, these pages call `self._register.action_band.hide()`.

### 2.2 Completed wiring summary

| Page class              | nav_id                 | Commands (prefix.verb)                                                            |
|-------------------------|------------------------|-----------------------------------------------------------------------------------|
| `JournalsPage`          | `journals`             | new_entry / edit_draft / delete_draft / post_entry / batch_post / refresh / print_entry / export_list |
| `SalesInvoicesPage`     | `sales_invoices`       | new / edit / cancel / post / refresh / print / export_list                        |
| `CustomersPage`         | `customers`            | new / edit / deactivate / refresh / export_list                                   |
| `SuppliersPage`         | `suppliers`            | new / edit / deactivate / refresh / export_list                                   |
| `PurchaseBillsPage`     | `purchase_bills`       | new / edit / cancel / post / refresh / print / export_list                        |
| `ChartOfAccountsPage`   | `chart_of_accounts`    | new / edit / deactivate / seed / import / role_mappings / refresh / export_list   |
| `TreasuryTransactions`  | `treasury_transactions`| new / edit / cancel / post / refresh / print / export_list                        |
| `TreasuryTransfersPage` | `treasury_transfers`   | new / edit / cancel / post / refresh / export_list                                |
| `JournalEntryWindow`    | `child:journal_entry`  | save / save_and_new / post / delete / print / close                               |

---

## 3. Phase 3A — Surface Registered, Page Not Yet Wired

These 8 contexts have ribbon surfaces in `RibbonRegistry` but the page classes have not yet added `RibbonHostMixin`. 

**Key difference from Phase 2:** All 7 inline-toolbar pages use a custom `QFrame` toolbar card built by `_build_toolbar()` or `_build_action_bar()` — **not** the `RegisterPage.action_band`. The wiring approach for these is:

1. Store the toolbar card widget as `self._toolbar_card` (or similar)
2. Call `self._toolbar_card.hide()` after ribbon takes over
3. Add `RibbonHostMixin` to class bases
4. Implement `_ribbon_commands()` and `ribbon_state()`
5. Append `self._notify_ribbon_state_changed()` to `_update_action_state`

### 3.1 `items` (ItemsPage) — RegisterPage.action_band pattern ✓

**Same wiring pattern as Phase 2 pages** — uses `RegisterPage.action_band`, not inline toolbar.

**Existing surface:** `_register_entity_register("items", prefix="items", ...)` → 6 items  
`items.new / items.edit / items.deactivate / (divider) / items.refresh / items.export_list`

**Page buttons (`_update_action_state`):**
- `_new_button` → `has_company`
- `_edit_button` → `has_company and selected`
- `_deactivate_button` → `has_company and selected and selected.is_active`

**`_ribbon_commands()` mapping:**
```python
{
    "items.new":        self._open_create_dialog,
    "items.edit":       self._open_edit_dialog,
    "items.deactivate": self._deactivate_selected_item,
    "items.refresh":    lambda: self.reload_items(),
    "items.export_list": self._export_item_list,
}
```

**`ribbon_state()` mapping:**
```python
{
    "items.new":        self._new_button.isEnabled(),
    "items.edit":       self._edit_button.isEnabled(),
    "items.deactivate": self._deactivate_button.isEnabled(),
    "items.refresh":    True,
    "items.export_list": has_company and bool(self._items),
}
```

**No surface change needed.**

---

### 3.2 `sales_orders` (SalesOrdersPage) — inline toolbar, surface needs update

**Toolbar style:** Inline `QHBoxLayout` inside `QFrame` card with buttons  
`_new_button / _edit_button / _confirm_button / _convert_button / _cancel_button / _refresh_button`

**Current surface (from `_register_document_register`):**  
`sales_orders.new / .edit / .cancel / .post (=Confirm) / (divider) / .refresh / .print / .export_list`

**Page actual actions (`_update_action_state`):**
- `_new_button` → `has_company + sales.orders.create`
- `_edit_button` → `has_company + selected + status=="draft" + sales.orders.edit`
- `_confirm_button` → `has_company + selected + status=="draft" + sales.orders.confirm`
- `_convert_button` → `has_company + selected + status=="confirmed" + sales.orders.convert + sales.invoices.create`
- `_cancel_button` → `has_company + selected + status in {draft,confirmed} + sales.orders.cancel`
- `_refresh_button` → always enabled

**Surface gap:** The registered surface maps `.post` to "Confirm Order" — but it is missing a **Convert to Invoice** button. The surface must be updated to add `sales_orders.convert`.

**Required surface definition update:**
```
new / edit / cancel-danger / (divider) / confirm / convert / (divider) / refresh / print / export_list
```

`sales_orders.new` | `sales_orders.edit` | `sales_orders.cancel` (danger) | divider |  
`sales_orders.confirm` | `sales_orders.convert` (label="Convert to Invoice") | divider |  
`sales_orders.refresh` | `sales_orders.print` | `sales_orders.export_list`

**Note:** Current `_register_document_register` helper cannot express this shape. This surface must be registered inline (not via the helper).

**`_ribbon_commands()` mapping:**
```python
{
    "sales_orders.new":     self._open_create_dialog,
    "sales_orders.edit":    self._open_edit_dialog,
    "sales_orders.confirm": self._confirm_order,
    "sales_orders.convert": self._convert_to_invoice,
    "sales_orders.cancel":  self._cancel_order,
    "sales_orders.refresh": self.reload_orders,
    "sales_orders.print":   self._print_order,
    "sales_orders.export_list": self._export_order_list,
}
```

---

### 3.3 `customer_quotes` (CustomerQuotesPage) — inline toolbar, surface needs update

**Toolbar style:** Inline toolbar card with buttons  
`_new_button / _edit_button / _issue_button / _accept_button / _reject_button / _convert_button / _cancel_button`

**Current surface:** `_register_document_register` gives:  
`new / edit / cancel / post(="Send Quote") / divider / refresh / print / export_list`

**Page actual actions:**
- `_new_button` → `has_company + sales.quotes.create`
- `_edit_button` → `has_company + selected + status=="draft" + sales.quotes.edit`
- `_issue_button` → `has_company + selected + status=="draft" + sales.quotes.issue`
- `_accept_button` → `has_company + selected + status=="issued" + sales.quotes.accept`
- `_reject_button` → `has_company + selected + status=="issued" + sales.quotes.reject`
- `_convert_button` → `has_company + selected + status=="accepted" + sales.quotes.convert + sales.invoices.create`
- `_cancel_button` → `has_company + selected + status in {draft,issued} + sales.quotes.cancel`

**Surface gap:** Missing `issue`, `accept`, `reject`, `convert` actions. The registered surface is severely under-defined for this multi-state workflow.

**Required surface definition (inline registration required):**
```
new / edit / cancel-danger / (divider) / issue / accept / reject / convert / (divider) / refresh / print / export_list
```

| command_id                    | label            | icon          | variant | default_enabled |
|-------------------------------|------------------|---------------|---------|-----------------|
| `customer_quotes.new`         | New Quote        | plus          | primary | true            |
| `customer_quotes.edit`        | Edit Draft       | edit          | —       | false           |
| `customer_quotes.cancel`      | Cancel Quote     | x             | danger  | false           |
| *(divider)*                   |                  |               |         |                 |
| `customer_quotes.issue`       | Issue Quote      | send          | —       | false           |
| `customer_quotes.accept`      | Accept           | check_square  | —       | false           |
| `customer_quotes.reject`      | Reject           | x_circle      | —       | false           |
| `customer_quotes.convert`     | Convert to Invoice | arrow_right | —       | false           |
| *(divider)*                   |                  |               |         |                 |
| `customer_quotes.refresh`     | Refresh          | refresh       | —       | true            |
| `customer_quotes.print`       | Print / Export   | printer       | —       | false           |
| `customer_quotes.export_list` | Export List      | download      | —       | false           |

---

### 3.4 `sales_credit_notes` (SalesCreditNotesPage) — inline toolbar, surface OK

**Toolbar style:** Inline `_build_toolbar()` card with  
`_new_btn / _edit_btn / _post_btn / _cancel_btn / _refresh_btn`

**Current surface:** `_register_document_register` →  
`new / edit / cancel / post / divider / refresh / print / export_list`

**Page actual actions (`_update_action_state`):**
- `_new_btn` → `has_company`
- `_edit_btn` → `is_draft` (status=="draft")
- `_post_btn` → `is_draft`
- `_cancel_btn` → `is_live` (status in "draft")

**Surface match:** Good enough — the registered surface's `print` and `export_list` buttons will be always-disabled (page has no print/export). This is acceptable. No print/export method exists on this page; `_ribbon_commands()` can map both to a no-op or omit them (silent on unknown is the current behavior).

**`_ribbon_commands()` mapping:**
```python
{
    "sales_credit_notes.new":    self._handle_new,
    "sales_credit_notes.edit":   self._handle_edit,
    "sales_credit_notes.post":   self._handle_post,
    "sales_credit_notes.cancel": self._handle_cancel,
    "sales_credit_notes.refresh": lambda: self.reload(),
    # .print and .export_list intentionally unmapped — silent on unknown
}
```

**`ribbon_state()` mapping:**
```python
{
    "sales_credit_notes.new":        self._new_btn.isEnabled(),
    "sales_credit_notes.edit":       self._edit_btn.isEnabled(),
    "sales_credit_notes.post":       self._post_btn.isEnabled(),
    "sales_credit_notes.cancel":     self._cancel_btn.isEnabled(),
    "sales_credit_notes.refresh":    True,
    "sales_credit_notes.print":      False,
    "sales_credit_notes.export_list": False,
}
```

---

### 3.5 `customer_receipts` (CustomerReceiptsPage) — inline toolbar, surface OK

**Toolbar style:** Inline toolbar card with  
`_new_button / _edit_button / _cancel_button / _post_button / _print_button / _export_list_button`

**Current surface:** `_register_document_register` → new / edit / cancel / post / divider / refresh / print / export_list

**Page actual actions:**
- `_new_button` → `has_company + sales.receipts.create`
- `_edit_button` → `is_draft + sales.receipts.edit`
- `_cancel_button` → `is_draft + sales.receipts.cancel`
- `_post_button` → `is_draft + sales.receipts.post`
- `_print_button` → `has_company and selected`
- `_export_list_button` → `has_company and bool(self._receipts)`

**Surface match:** Full match. Surface includes all needed actions.

**`_ribbon_commands()` mapping:**
```python
{
    "customer_receipts.new":         self._open_create_dialog,
    "customer_receipts.edit":        self._open_edit_dialog,
    "customer_receipts.cancel":      self._cancel_receipt,
    "customer_receipts.post":        self._post_receipt,
    "customer_receipts.refresh":     self.reload_receipts,
    "customer_receipts.print":       self._print_receipt,
    "customer_receipts.export_list": self._export_receipt_list,
}
```

---

### 3.6 `purchase_orders` (PurchaseOrdersPage) — inline toolbar, surface needs update

**Toolbar style:** Inline toolbar card with  
`_new_button / _edit_button / _send_button / _acknowledge_button / _convert_button / _cancel_button`

**Current surface:** `_register_document_register` →  
`new / edit / cancel / post(="Confirm Order") / divider / refresh / print / export_list`

**Page actual actions:**
- `_new_button` → `has_company + purchases.orders.create`
- `_edit_button` → `has_company + selected + status=="draft" + purchases.orders.edit`
- `_send_button` → `has_company + selected + status=="draft" + purchases.orders.send`
- `_acknowledge_button` → `has_company + selected + status=="sent" + purchases.orders.acknowledge`
- `_convert_button` → `has_company + selected + status=="acknowledged" + purchases.orders.convert + purchases.bills.create`
- `_cancel_button` → `has_company + selected + status in {draft,sent} + purchases.orders.cancel`

**Surface gap:** Missing `send`, `acknowledge`, `convert` actions. Current `post` button does not map to anything meaningful on this page.

**Required surface definition (inline registration required):**
```
new / edit / cancel-danger / (divider) / send / acknowledge / convert / (divider) / refresh / print / export_list
```

| command_id                     | label              | icon         | variant | default_enabled |
|--------------------------------|--------------------|--------------|---------|-----------------|
| `purchase_orders.new`          | New Order          | plus         | primary | true            |
| `purchase_orders.edit`         | Edit Order         | edit         | —       | false           |
| `purchase_orders.cancel`       | Cancel Order       | x            | danger  | false           |
| *(divider)*                    |                    |              |         |                 |
| `purchase_orders.send`         | Send to Supplier   | send         | —       | false           |
| `purchase_orders.acknowledge`  | Acknowledge        | check_square | —       | false           |
| `purchase_orders.convert`      | Convert to Bill    | arrow_right  | —       | false           |
| *(divider)*                    |                    |              |         |                 |
| `purchase_orders.refresh`      | Refresh            | refresh      | —       | true            |
| `purchase_orders.print`        | Print / Export     | printer      | —       | false           |
| `purchase_orders.export_list`  | Export List        | download     | —       | false           |

---

### 3.7 `purchase_credit_notes` (PurchaseCreditNotesPage) — inline toolbar, surface OK

**Toolbar style:** Inline toolbar card with `_new_btn / _edit_btn / _post_btn / _cancel_btn`

**Current surface:** `_register_document_register` → new / edit / cancel / post / divider / refresh / print / export_list

**Page actual actions:**
- `_new_btn` → `has_company`
- `_edit_btn` → `is_draft`
- `_post_btn` → `is_draft`
- `_cancel_btn` → `is_draft`

**Surface match:** Good enough. Print/export will be disabled-only (no handlers). Acceptable.

**`_ribbon_commands()` mapping:**
```python
{
    "purchase_credit_notes.new":    self._handle_new,
    "purchase_credit_notes.edit":   self._handle_edit,
    "purchase_credit_notes.post":   self._handle_post,
    "purchase_credit_notes.cancel": self._handle_cancel,
    "purchase_credit_notes.refresh": lambda: self.reload(),
    # .print / .export_list unmapped — silent ignore
}
```

---

### 3.8 `supplier_payments` (SupplierPaymentsPage) — inline toolbar, surface OK

**Toolbar style:** Inline toolbar card with  
`_new_button / _edit_button / _cancel_button / _post_button / _print_button / _export_list_button`

**Current surface:** `_register_document_register` → new / edit / cancel / post / divider / refresh / print / export_list

**Page actual actions:**
- `_new_button` → `has_company + purchases.payments.create`
- `_edit_button` → `is_draft + purchases.payments.edit`
- `_cancel_button` → `is_draft + purchases.payments.cancel`
- `_post_button` → `is_draft + purchases.payments.post`
- `_print_button` → `has_company and selected`
- `_export_list_button` → `has_company and bool(self._payments)`

**Surface match:** Full match.

**`_ribbon_commands()` mapping:**
```python
{
    "supplier_payments.new":         self._open_create_dialog,
    "supplier_payments.edit":        self._open_edit_dialog,
    "supplier_payments.cancel":      self._cancel_payment,
    "supplier_payments.post":        self._post_payment,
    "supplier_payments.refresh":     self.reload_payments,
    "supplier_payments.print":       self._print_payment,
    "supplier_payments.export_list": self._export_payment_list,
}
```

---

## 4. Phase 3B — No Surface, Reference & Core Pages

These pages do not yet have ribbon surfaces or wiring. They are simpler entity-register or management pages.

### 4.1 `companies` (CompanyListPage)

**Toolbar style:** RegisterPage.action_band (`_new_button`, `_edit_button` populated via `_populate_action_band`)

**Buttons:**
- `_new_button` → `companies.create` permission
- `_edit_button` → `selected + companies.edit` permission

**Proposed surface:**

| command_id       | label       | icon    | variant | default_enabled |
|------------------|-------------|---------|---------|-----------------|
| `companies.new`  | New Company | plus    | primary | true            |
| `companies.edit` | Edit        | edit    | —       | false           |
| *(divider)*      |             |         |         |                 |
| `companies.refresh` | Refresh  | refresh | —       | true            |

**Implementation:** Same as Phase 2 (action_band.hide + RibbonHostMixin). No permission check in ribbon — delegate to the existing action handler which guards permissions internally.

---

### 4.2 `payment_terms` (PaymentTermsPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company + reference.payment_terms.create`
- `_edit_button` → `selected + has_company + reference.payment_terms.edit`
- `_deactivate_button` → `selected + has_company + selected.is_active + reference.payment_terms.deactivate`

**Proposed surface (entity_register shape):**

| command_id                  | label            | icon    | variant | default_enabled |
|-----------------------------|------------------|---------|---------|-----------------|
| `payment_terms.new`         | New Terms        | plus    | primary | true            |
| `payment_terms.edit`        | Edit             | edit    | —       | false           |
| `payment_terms.deactivate`  | Deactivate       | x       | danger  | false           |
| *(divider)*                 |                  |         |         |                 |
| `payment_terms.refresh`     | Refresh          | refresh | —       | true            |
| `payment_terms.export_list` | Export List      | download| —       | false           |

---

### 4.3 `tax_codes` (TaxCodesPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company + reference.tax_codes.create`
- `_edit_button` → `selected + has_company + reference.tax_codes.edit`
- `_deactivate_button` → `selected + has_company + selected.is_active + reference.tax_codes.deactivate`
- `_mapping_button` → `has_company + (tax_mappings.view OR tax_mappings.manage)` → opens tax mappings dialog

**Proposed surface:**

| command_id               | label          | icon        | variant | default_enabled |
|--------------------------|----------------|-------------|---------|-----------------|
| `tax_codes.new`          | New Tax Code   | plus        | primary | true            |
| `tax_codes.edit`         | Edit           | edit        | —       | false           |
| `tax_codes.deactivate`   | Deactivate     | x           | danger  | false           |
| *(divider)*              |                |             |         |                 |
| `tax_codes.tax_mappings` | Tax Mappings   | list_checks | —       | true            |
| *(divider)*              |                |             |         |                 |
| `tax_codes.refresh`      | Refresh        | refresh     | —       | true            |
| `tax_codes.export_list`  | Export List    | download    | —       | false           |

---

### 4.4 `document_sequences` (DocumentSequencesPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company + reference.document_sequences.create`
- `_edit_button` → `selected + has_company + reference.document_sequences.edit`
- `_preview_button` → `selected + has_company + reference.document_sequences.preview`
- `_deactivate_button` → `selected + has_company + selected.is_active + reference.document_sequences.deactivate`

**Proposed surface:**

| command_id                      | label           | icon    | variant | default_enabled |
|---------------------------------|-----------------|---------|---------|-----------------|
| `document_sequences.new`        | New Sequence    | plus    | primary | true            |
| `document_sequences.edit`       | Edit            | edit    | —       | false           |
| `document_sequences.preview`    | Preview         | eye     | —       | false           |
| `document_sequences.deactivate` | Deactivate      | x       | danger  | false           |
| *(divider)*                     |                 |         |         |                 |
| `document_sequences.refresh`    | Refresh         | refresh | —       | true            |

---

### 4.5 `account_role_mappings` (AccountRoleMappingsPage)

**Page style:** This is a **form-style page**, not a list register. It shows the current mapping grid with a save/clear action on each row. There is no list table to select rows from.

**Buttons:**
- `_save_button` → in-row save
- `_clear_button` → in-row clear
- `_refresh_button` → reload
- `_return_button` / `dismiss_btn` → navigation buttons (not suitable for ribbon)

**Ribbon recommendation:** Minimal utility surface — Refresh only. Save/Clear are inline actions within the form grid and should remain inline. Navigation buttons (Return/Dismiss) do not belong in the ribbon.

**Proposed surface:**

| command_id                       | label        | icon    | variant | default_enabled |
|----------------------------------|--------------|---------|---------|-----------------|
| `account_role_mappings.refresh`  | Refresh      | refresh | —       | true            |
| `account_role_mappings.save_all` | Save All     | save    | primary | false           |

> **Note:** The current page has per-row save, not a global Save All. A `Save All` ribbon button would require a new page method that persists all dirty rows at once. This is a future enhancement — for the initial ribbon pass, just register `refresh` and leave `save_all` default_enabled=false as a placeholder.

---

### 4.6 `fiscal_periods` (FiscalPeriodsPage)

**Toolbar style:** RegisterPage.action_band (uses the standard RegisterPage pattern)

**Buttons:**
- `_new_year_button` → `has_company + fiscal.years.create`
- `_generate_periods_button` → `has_company + fiscal_year selected + no periods yet + fiscal.periods.generate`
- `_open_button` → `has_company + period selected + status=="CLOSED" + fiscal.periods.open`
- `_close_button` → `has_company + period selected + status=="OPEN" + fiscal.periods.close`
- `_reopen_button` → `has_company + period selected + status=="CLOSED" + fiscal.periods.reopen`
- `_lock_button` → `has_company + period selected + status=="CLOSED" + fiscal.periods.lock`

**Proposed surface:**

| command_id                          | label              | icon        | variant | default_enabled |
|-------------------------------------|--------------------|-------------|---------|-----------------|
| `fiscal_periods.new_year`           | New Fiscal Year    | plus        | primary | true            |
| `fiscal_periods.generate_periods`   | Generate Periods   | list_checks | —       | false           |
| *(divider)*                         |                    |             |         |                 |
| `fiscal_periods.open_period`        | Open Period        | unlock      | —       | false           |
| `fiscal_periods.close_period`       | Close Period       | lock        | —       | false           |
| `fiscal_periods.reopen_period`      | Re-open Period     | unlock      | —       | false           |
| `fiscal_periods.lock_period`        | Lock Period        | lock        | danger  | false           |
| *(divider)*                         |                    |             |         |                 |
| `fiscal_periods.refresh`            | Refresh            | refresh     | —       | true            |

**Implementation note:** All buttons except `new_year` and `refresh` are state-sensitive to the selected period. The period list is a split-pane (years left, periods right) — both tables drive button state.

---

### 4.7 `financial_accounts` (FinancialAccountsPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company`
- `_edit_button` → `has_company + selected`
- `_toggle_active_button` → `has_company + selected`
- `_export_list_button` → `has_company + bool(self._accounts)`

**Proposed surface (entity_register shape + toggle):**

| command_id                         | label           | icon    | variant | default_enabled |
|------------------------------------|-----------------|---------|---------|-----------------|
| `financial_accounts.new`           | New Account     | plus    | primary | true            |
| `financial_accounts.edit`          | Edit            | edit    | —       | false           |
| `financial_accounts.toggle_active` | Toggle Active   | toggle  | —       | false           |
| *(divider)*                        |                 |         |         |                 |
| `financial_accounts.refresh`       | Refresh         | refresh | —       | true            |
| `financial_accounts.export_list`   | Export List     | download| —       | false           |

---

## 5. Phase 4 — Treasury, Inventory, Fixed Assets, Contracts, Projects, Administration

### 5.1 `statement_lines` (StatementLinesPage)

**Page style:** Operational list + import. No standard entity CRUD.

**Buttons:**
- `_import_button` → `has_company`
- `_add_manual_button` → `has_company`

**Proposed surface:**

| command_id                       | label              | icon     | variant | default_enabled |
|----------------------------------|--------------------|----------|---------|-----------------|
| `statement_lines.import`         | Import Statement   | download | primary | true            |
| `statement_lines.add_manual`     | Add Manual Line    | plus     | —       | true            |
| *(divider)*                      |                    |          |         |                 |
| `statement_lines.refresh`        | Refresh            | refresh  | —       | true            |

---

### 5.2 `bank_reconciliation` (BankReconciliationPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company`
- `_complete_button` → `is_draft` (session status=="draft")
- `_summary_button` → `has_selection`

**Proposed surface:**

| command_id                        | label              | icon        | variant | default_enabled |
|-----------------------------------|--------------------|-------------|---------|-----------------|
| `bank_reconciliation.new`         | New Session        | plus        | primary | true            |
| `bank_reconciliation.complete`    | Complete           | check_square| —       | false           |
| `bank_reconciliation.summary`     | Print Summary      | printer     | —       | false           |
| *(divider)*                       |                    |             |         |                 |
| `bank_reconciliation.refresh`     | Refresh            | refresh     | —       | true            |

---

### 5.3 `uom_categories` (UomCategoriesPage)

**Toolbar style:** Inline card with `_new_btn / _edit_btn / refresh_btn`

**Proposed surface (minimal entity register):**

| command_id               | label          | icon    | variant | default_enabled |
|--------------------------|----------------|---------|---------|-----------------|
| `uom_categories.new`     | New Category   | plus    | primary | true            |
| `uom_categories.edit`    | Edit           | edit    | —       | false           |
| *(divider)*              |                |         |         |                 |
| `uom_categories.refresh` | Refresh        | refresh | —       | true            |

---

### 5.4 `units_of_measure` (UnitsOfMeasurePage)

**Toolbar style:** Inline card with `_new_btn / _edit_btn / refresh_btn`

**Proposed surface:**

| command_id              | label          | icon    | variant | default_enabled |
|-------------------------|----------------|---------|---------|-----------------|
| `units_of_measure.new`  | New UoM        | plus    | primary | true            |
| `units_of_measure.edit` | Edit           | edit    | —       | false           |
| *(divider)*             |                |         |         |                 |
| `units_of_measure.refresh` | Refresh     | refresh | —       | true            |

---

### 5.5 `item_categories` (ItemCategoriesPage)

**Toolbar style:** Inline card with `_new_btn / _edit_btn / refresh_btn`

**Proposed surface:**

| command_id               | label          | icon    | variant | default_enabled |
|--------------------------|----------------|---------|---------|-----------------|
| `item_categories.new`    | New Category   | plus    | primary | true            |
| `item_categories.edit`   | Edit           | edit    | —       | false           |
| *(divider)*              |                |         |         |                 |
| `item_categories.refresh`| Refresh        | refresh | —       | true            |

---

### 5.6 `inventory_locations` (InventoryLocationsPage)

**Toolbar style:** Inline card with `_new_btn / _edit_btn / refresh_btn`

**Proposed surface:**

| command_id                    | label           | icon    | variant | default_enabled |
|-------------------------------|-----------------|---------|---------|-----------------|
| `inventory_locations.new`     | New Location    | plus    | primary | true            |
| `inventory_locations.edit`    | Edit            | edit    | —       | false           |
| *(divider)*                   |                 |         |         |                 |
| `inventory_locations.refresh` | Refresh         | refresh | —       | true            |

---

### 5.7 `inventory_documents` (InventoryDocumentsPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company`
- `_edit_button` → `is_draft`
- `_cancel_button` → `is_draft`
- `_post_button` → `is_draft`

**Proposed surface (document_register shape):**

| command_id                     | label           | icon        | variant | default_enabled |
|--------------------------------|-----------------|-------------|---------|-----------------|
| `inventory_documents.new`      | New Document    | plus        | primary | true            |
| `inventory_documents.edit`     | Edit Draft      | edit        | —       | false           |
| `inventory_documents.cancel`   | Cancel Draft    | x           | danger  | false           |
| *(divider)*                    |                 |             |         |                 |
| `inventory_documents.post`     | Post Document   | check_square| —       | false           |
| *(divider)*                    |                 |             |         |                 |
| `inventory_documents.refresh`  | Refresh         | refresh     | —       | true            |

---

### 5.8 `stock_position` (InventoryStockView)

**Page style:** Read-only stock-on-hand list. Only action is `_refresh_button`.

**Proposed surface (minimal — refresh only):**

| command_id              | label   | icon    | variant | default_enabled |
|-------------------------|---------|---------|---------|-----------------|
| `stock_position.refresh`| Refresh | refresh | —       | true            |

> **Alternative:** Do not register a ribbon surface at all. The ribbon bar hides itself when no surface is found for the current nav_id. This is acceptable for a read-only view. Preferred: register the minimal surface so the ribbon area does not flash blank.

---

### 5.9 `asset_categories` (AssetCategoriesPage)

**Toolbar style:** Inline card with `_new_btn / _edit_btn / _deactivate_btn / refresh_btn`

**Note:** No `_update_action_state` method on this page — buttons are enabled/disabled directly on table selection in `itemSelectionChanged`. When wiring, the `ribbon_state()` method must read `.isEnabled()` from the buttons.

**Proposed surface:**

| command_id                   | label          | icon    | variant | default_enabled |
|------------------------------|----------------|---------|---------|-----------------|
| `asset_categories.new`       | New Category   | plus    | primary | true            |
| `asset_categories.edit`      | Edit           | edit    | —       | false           |
| `asset_categories.deactivate`| Deactivate     | x       | danger  | false           |
| *(divider)*                  |                |         |         |                 |
| `asset_categories.refresh`   | Refresh        | refresh | —       | true            |

**Implementation note:** This page uses a different state-update pattern (no `_update_action_state` method). The `_notify_ribbon_state_changed()` call must be wired into the `itemSelectionChanged` signal handler and the reload method instead.

---

### 5.10 `assets` (AssetsPage)

**Toolbar style:** Inline card with `_new_btn / _edit_btn / _schedule_btn / refresh_btn`

**Note:** No `_update_action_state` method — same situation as `asset_categories`.

**Proposed surface:**

| command_id           | label            | icon    | variant | default_enabled |
|----------------------|------------------|---------|---------|-----------------|
| `assets.new`         | New Asset        | plus    | primary | true            |
| `assets.edit`        | Edit Asset       | edit    | —       | false           |
| `assets.schedule`    | Preview Schedule | eye     | —       | false           |
| *(divider)*          |                  |         |         |                 |
| `assets.refresh`     | Refresh          | refresh | —       | true            |

---

### 5.11 `depreciation_runs` (DepreciationRunsPage)

**Toolbar style:** Inline card with `_new_btn / _open_btn / refresh_btn`

**Note:** No `_update_action_state` method.

**Proposed surface:**

| command_id                 | label      | icon        | variant | default_enabled |
|----------------------------|------------|-------------|---------|-----------------|
| `depreciation_runs.new`    | New Run    | plus        | primary | true            |
| `depreciation_runs.open`   | Open Run   | folder_open | —       | false           |
| *(divider)*                |            |             |         |                 |
| `depreciation_runs.refresh`| Refresh    | refresh     | —       | true            |

---

### 5.12 `contracts` (ContractsPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company`
- `_edit_button` → `selected + has_company`
- `_activate_button` → `selected + has_company + status=="draft"`
- `_cancel_button` → `selected + has_company + status in {draft, active, on_hold}`
- `_change_orders_button` → `selected + has_company`

**Proposed surface:**

| command_id                    | label           | icon        | variant | default_enabled |
|-------------------------------|-----------------|-------------|---------|-----------------|
| `contracts.new`               | New Contract    | plus        | primary | true            |
| `contracts.edit`              | Edit Contract   | edit        | —       | false           |
| `contracts.cancel`            | Cancel          | x           | danger  | false           |
| *(divider)*                   |                 |             |         |                 |
| `contracts.activate`          | Activate        | check_square| —       | false           |
| `contracts.change_orders`     | Change Orders   | list_checks | —       | false           |
| *(divider)*                   |                 |             |         |                 |
| `contracts.refresh`           | Refresh         | refresh     | —       | true            |

---

### 5.13 `projects` (ProjectsPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company`
- `_edit_button` → `selected + has_company`
- `_activate_button` → `selected + has_company + status=="draft"`
- `_cancel_button` → `selected + has_company + status in {draft, active, on_hold}`
- `_jobs_button` → `selected + has_company`
- `_cost_codes_button` → `has_company` (global, not selection-dependent)
- `_budgets_button` → `selected + has_company`
- `_commitments_button` → `selected + has_company`

**Proposed surface:**

| command_id               | label          | icon        | variant | default_enabled |
|--------------------------|----------------|-------------|---------|-----------------|
| `projects.new`           | New Project    | plus        | primary | true            |
| `projects.edit`          | Edit Project   | edit        | —       | false           |
| `projects.cancel`        | Cancel         | x           | danger  | false           |
| *(divider)*              |                |             |         |                 |
| `projects.activate`      | Activate       | check_square| —       | false           |
| *(divider)*              |                |             |         |                 |
| `projects.jobs`          | Jobs           | list        | —       | false           |
| `projects.cost_codes`    | Cost Codes     | list_checks | —       | true            |
| `projects.budgets`       | Budgets        | bar_chart   | —       | false           |
| `projects.commitments`   | Commitments    | file_text   | —       | false           |
| *(divider)*              |                |             |         |                 |
| `projects.refresh`       | Refresh        | refresh     | —       | true            |

---

### 5.14 `administration` (AdministrationPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `has_company + administration.users.create`
- `_edit_button` → `has_company + selected + administration.users.edit`
- `_password_button` → `has_company + selected + administration.users.edit`
- `_toggle_active_button` → `has_company + selected + not_self + administration.users.deactivate`
- `_roles_button` → `has_company + selected + not_self + administration.user_roles.assign`

**Proposed surface:**

| command_id                        | label            | icon    | variant | default_enabled |
|-----------------------------------|------------------|---------|---------|-----------------|
| `administration.new_user`         | New User         | plus    | primary | true            |
| `administration.edit_user`        | Edit User        | edit    | —       | false           |
| `administration.change_password`  | Change Password  | key     | —       | false           |
| `administration.toggle_active`    | Deactivate       | toggle  | danger  | false           |
| *(divider)*                       |                  |         |         |                 |
| `administration.assign_roles`     | Assign Roles     | shield  | —       | false           |
| *(divider)*                       |                  |         |         |                 |
| `administration.refresh`          | Refresh          | refresh | —       | true            |

**Implementation note:** The `toggle_active` label is dynamic (`"Activate"` or `"Deactivate"` depending on selected user state). This label mutation is only needed in the toolbar button text; the ribbon button label is static. Consider using the ribbon button tooltip to convey the current target state, or a fixed label `"Toggle Active"`.

---

### 5.15 `roles` (RolesPage)

**Toolbar style:** RegisterPage.action_band

**Buttons:**
- `_new_button` → `administration.roles.create`
- `_edit_button` → `selected + administration.roles.edit`
- `_permissions_button` → `selected + administration.role_permissions.assign`
- `_delete_button` → `selected + not_system + administration.roles.delete`

**Proposed surface:**

| command_id              | label        | icon        | variant | default_enabled |
|-------------------------|--------------|-------------|---------|-----------------|
| `roles.new`             | New Role     | plus        | primary | true            |
| `roles.edit`            | Edit Role    | edit        | —       | false           |
| `roles.delete`          | Delete Role  | trash       | danger  | false           |
| *(divider)*             |              |             |         |                 |
| `roles.permissions`     | Permissions  | shield      | —       | false           |
| *(divider)*             |              |             |         |                 |
| `roles.refresh`         | Refresh      | refresh     | —       | true            |

---

### 5.16 `organisation_settings` (OrganisationSettingsPage)

**Page style:** Detail form (single company detail view, not a list register)

**Buttons:**
- `_modify_button` → `has_company` (opens sys-admin auth gate then edit dialog)
- `_preferences_button` → `has_company + companies.preferences.manage`

**Proposed surface:**

| command_id                               | label         | icon     | variant | default_enabled |
|------------------------------------------|---------------|----------|---------|-----------------|
| `organisation_settings.modify`           | Modify        | edit     | primary | false           |
| `organisation_settings.preferences`     | Preferences   | settings | —       | false           |
| *(divider)*                              |               |          |         |                 |
| `organisation_settings.refresh`         | Refresh       | refresh  | —       | true            |

---

## 6. Phase 5 — Payroll Workspaces

The payroll pages are **tabbed workspace pages**, each containing multiple sub-panels with their own toolbar bars. The ribbon approach for these must be carefully considered:

**Option A — Tab-aware ribbon:** The ribbon surface switches based on the active tab within the workspace. This requires the page to signal ribbon state changes on tab selection. Complex but most coherent UX.

**Option B — Global workspace surface:** One ribbon surface per payroll workspace, showing the union of all major actions. Tab-irrelevant buttons are disabled.

**Option C — No ribbon for payroll workspaces:** Hide the ribbon (no surface registered). Payroll workspaces are complex enough that their inline toolbars carry the UX. This avoids the problem.

**Recommendation:** Use Option C for the initial ribbon pass. Payroll workspaces have internal tab toolbars that are already well-structured. A single flat ribbon cannot cleanly express the tabbed sub-workflow. Register no surfaces for `payroll_setup`, `payroll_calculation`, `payroll_accounting`, `payroll_operations`. The ribbon bar hides itself when no surface exists.

If a future slice explicitly asks for payroll ribbon integration, revisit with Option A and a tab-change signal from each workspace.

---

## 7. Deferred / Not Applicable

| nav_id                  | Reason                                                                                            |
|-------------------------|---------------------------------------------------------------------------------------------------|
| `dashboard`             | No user actions — KPI cards and navigation shortcuts only                                          |
| `reports`               | Tab-based report launcher. Each report opens its own window. No register-style toolbar applicable. |
| `project_variance_analysis` | Read-only/filtered report workspace                                                           |
| `contract_summary`      | Read-only/filtered report workspace                                                               |
| `audit_log`             | No page file found in administration/ui — may not yet exist                                       |
| `backup_restore`        | Two-phase form (export / import). Inline workflow buttons are more appropriate than a ribbon.      |
| `customer_detail`       | Detail workspace with tabs. No register-style toolbar — ribbon not applicable for first pass.      |
| `supplier_detail`       | Same as customer_detail                                                                           |
| `account_detail`        | Same as customer_detail                                                                           |
| `item_detail`           | Same as customer_detail                                                                           |
| `sales_invoice_detail`  | Future document workspace — TBD when implemented                                                  |
| `purchase_bill_detail`  | Future document workspace — TBD when implemented                                                  |

---

## 8. Implementation Patterns Reference

### 8.1 RegisterPage.action_band pattern (Phase 2 style)

Used by pages that subclass `RegisterPage` and call `_populate_action_band`.

```python
class FooPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry, parent=None):
        super().__init__(parent)
        # ... existing __init__ ...
        self._register.action_band.hide()  # after _populate_action_band

    def _ribbon_commands(self) -> dict:
        return {
            "foo.new": self._open_create_dialog,
            "foo.edit": self._open_edit_dialog,
            "foo.refresh": lambda: self.reload(),
        }

    def ribbon_state(self) -> dict:
        return {
            "foo.new": self._new_button.isEnabled(),
            "foo.edit": self._edit_button.isEnabled(),
            "foo.refresh": True,
        }

    def _update_action_state(self) -> None:
        # ... existing logic ...
        self._notify_ribbon_state_changed()
```

### 8.2 Inline toolbar card pattern (Phase 3A style)

Used by pages that build their own toolbar QFrame.

```python
class FooPage(RibbonHostMixin, QWidget):
    def __init__(self, service_registry, parent=None):
        super().__init__(parent)
        # ... build layout ...
        self._toolbar_card = self._build_toolbar()   # store reference
        root_layout.addWidget(self._toolbar_card)
        self._toolbar_card.hide()                     # hide after ribbon takes over
        root_layout.addWidget(self._build_content(), 1)

    def _ribbon_commands(self) -> dict:
        return {
            "foo.new": self._handle_new,
            # ...
        }

    def ribbon_state(self) -> dict:
        return {
            "foo.new": self._new_btn.isEnabled(),
            # ...
        }

    def _update_action_state(self) -> None:
        # ... existing logic ...
        self._notify_ribbon_state_changed()
```

**Critical:** The inline toolbar card reference must be captured as `self._toolbar_card` (or similar) so it can be hidden. Some pages currently do not store this reference. The `_build_toolbar()` method must be updated to `return card` AND `self._toolbar_card = card` before calling `hide()`.

### 8.3 Pages without `_update_action_state` (assets, asset_categories, depreciation_runs)

These pages update button state directly in table selection handlers. For ribbon integration:

1. Add `_update_action_state(self)` method that reads from existing button `.isEnabled()` states
2. Connect `self._table.itemSelectionChanged` to `_update_action_state`
3. Call `_notify_ribbon_state_changed()` at the end of `_update_action_state`
4. Call `_update_action_state()` at the end of `reload()`

### 8.4 Child window surfaces (`child:<kind>`)

All child document windows subclass `ChildWindowBase` which is already a full `IRibbonHost`.  
Only `child:journal_entry` is registered and wired. Future child windows:

| Kind               | Surface key                  | Status   |
|--------------------|------------------------------|----------|
| `journal_entry`    | `child:journal_entry`        | ✅ Done   |
| (future document)  | `child:<doc_type>`           | Planned  |

---

## 9. Surface Update Checklist

Surfaces that already exist in `RibbonRegistry` but need **updating** before the page can be wired:

| Surface key      | Problem                                     | Required change                              |
|------------------|---------------------------------------------|----------------------------------------------|
| `sales_orders`   | Missing `convert` action                   | Replace with inline registration — add `sales_orders.confirm`, `sales_orders.convert` |
| `customer_quotes`| Missing `issue`, `accept`, `reject`, `convert` | Replace with inline registration — full multi-state surface |
| `purchase_orders`| Missing `send`, `acknowledge`, `convert`   | Replace with inline registration — add workflow state buttons |

The `_register_document_register` helper cannot express these multi-state workflows. These three surfaces must be replaced with explicit inline `RibbonSurfaceDef(...)` calls in `_register_built_in`.

---

## 10. Ribbon Registry Registration Map

For tracking which surfaces will be added to `RibbonRegistry._register_built_in()`:

| Phase | Surface keys to add                                                                                                                     |
|-------|-----------------------------------------------------------------------------------------------------------------------------------------|
| 3A    | Update: `sales_orders`, `customer_quotes`, `purchase_orders` (rebuild as inline defs)                                                  |
| 3B    | Add: `companies`, `payment_terms`, `tax_codes`, `document_sequences`, `account_role_mappings`, `fiscal_periods`, `financial_accounts`   |
| 4     | Add: `statement_lines`, `bank_reconciliation`, `uom_categories`, `units_of_measure`, `item_categories`, `inventory_locations`, `inventory_documents`, `stock_position`, `asset_categories`, `assets`, `depreciation_runs`, `contracts`, `projects`, `administration`, `roles`, `organisation_settings` |
| 5     | Payroll: deferred (Option C — no surfaces)                                                                                              |
