"""Step 3 — Default accounts and tax codes, then create the item."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.inventory.dto.item_commands import CreateItemCommand
from seeker_accounting.modules.wizards.new_item import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class AccountsStep(WizardStep):
    key = "accounts"
    title = "Accounts"
    subtitle = "Default GL accounts and tax codes for posting."

    commits_on_advance = True

    def __init__(self) -> None:
        super().__init__()
        self._revenue: QComboBox | None = None
        self._cogs: QComboBox | None = None
        self._inventory: QComboBox | None = None
        self._expense: QComboBox | None = None
        self._sales_tax: QComboBox | None = None
        self._purchase_tax: QComboBox | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._revenue = QComboBox(root)
        form.addRow(QLabel("Revenue account:", root), self._revenue)

        self._cogs = QComboBox(root)
        form.addRow(QLabel("COGS account:", root), self._cogs)

        self._inventory = QComboBox(root)
        form.addRow(QLabel("Inventory account:", root), self._inventory)

        self._expense = QComboBox(root)
        form.addRow(QLabel("Expense account:", root), self._expense)

        self._sales_tax = QComboBox(root)
        form.addRow(QLabel("Sales tax code:", root), self._sales_tax)

        self._purchase_tax = QComboBox(root)
        form.addRow(QLabel("Purchase tax code:", root), self._purchase_tax)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def _populate_accounts(self, combo: QComboBox, accounts) -> None:
        combo.addItem("(none)", None)
        for a in accounts:
            if not a.is_active or not a.allow_manual_posting:
                continue
            combo.addItem(f"{a.account_code} \u2014 {a.account_name}", a.id)

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        if self._revenue is not None and self._revenue.count() == 0:
            accounts = context.service_registry.chart_of_accounts_service.list_accounts(
                company_id, active_only=True
            )
            for combo in (self._revenue, self._cogs, self._inventory, self._expense):
                self._populate_accounts(combo, accounts)
            tax_codes = context.service_registry.tax_setup_service.list_tax_codes(
                company_id, active_only=True
            )
            for combo in (self._sales_tax, self._purchase_tax):
                combo.addItem("(none)", None)
                for t in tax_codes:
                    rate = f" {t.rate_percent}%" if t.rate_percent is not None else ""
                    combo.addItem(f"{t.code} \u2014 {t.name}{rate}", t.id)
        for combo, key in (
            (self._revenue, K.KEY_REVENUE_ACCOUNT_ID),
            (self._cogs, K.KEY_COGS_ACCOUNT_ID),
            (self._inventory, K.KEY_INVENTORY_ACCOUNT_ID),
            (self._expense, K.KEY_EXPENSE_ACCOUNT_ID),
            (self._sales_tax, K.KEY_SALES_TAX_CODE_ID),
            (self._purchase_tax, K.KEY_PURCHASE_TAX_CODE_ID),
        ):
            if combo is None:
                continue
            prior = state.get(key)
            if isinstance(prior, int):
                idx = combo.findData(prior)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def write_back(self, state: WizardState) -> None:
        for combo, key in (
            (self._revenue, K.KEY_REVENUE_ACCOUNT_ID),
            (self._cogs, K.KEY_COGS_ACCOUNT_ID),
            (self._inventory, K.KEY_INVENTORY_ACCOUNT_ID),
            (self._expense, K.KEY_EXPENSE_ACCOUNT_ID),
            (self._sales_tax, K.KEY_SALES_TAX_CODE_ID),
            (self._purchase_tax, K.KEY_PURCHASE_TAX_CODE_ID),
        ):
            if combo is None:
                state[key] = None
                continue
            data = combo.currentData()
            state[key] = int(data) if isinstance(data, int) else None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        type_code = state.get(K.KEY_ITEM_TYPE_CODE)
        if type_code == "stock":
            if not state.get(K.KEY_INVENTORY_ACCOUNT_ID):
                return StepValidationResult.fail("Stock items require an inventory account.")
            if not state.get(K.KEY_COGS_ACCOUNT_ID):
                return StepValidationResult.fail("Stock items require a COGS account.")
        return StepValidationResult.ok()

    def commit(self, context: WizardContext, state: WizardState) -> None:
        if isinstance(state.get(K.KEY_ITEM_ID), int):
            return
        company_id = context.require_company_id()
        rq_raw = state.get(K.KEY_REORDER_LEVEL_QUANTITY)
        cmd = CreateItemCommand(
            item_code=str(state[K.KEY_ITEM_CODE]),
            item_name=str(state[K.KEY_ITEM_NAME]),
            item_type_code=str(state[K.KEY_ITEM_TYPE_CODE]),
            unit_of_measure_id=int(state[K.KEY_UNIT_OF_MEASURE_ID]),
            unit_of_measure_code=str(state.get(K.KEY_UNIT_OF_MEASURE_CODE) or "UNIT"),
            item_category_id=state.get(K.KEY_ITEM_CATEGORY_ID),
            inventory_cost_method_code=state.get(K.KEY_INVENTORY_COST_METHOD_CODE),
            inventory_account_id=state.get(K.KEY_INVENTORY_ACCOUNT_ID),
            cogs_account_id=state.get(K.KEY_COGS_ACCOUNT_ID),
            expense_account_id=state.get(K.KEY_EXPENSE_ACCOUNT_ID),
            revenue_account_id=state.get(K.KEY_REVENUE_ACCOUNT_ID),
            purchase_tax_code_id=state.get(K.KEY_PURCHASE_TAX_CODE_ID),
            sales_tax_code_id=state.get(K.KEY_SALES_TAX_CODE_ID),
            reorder_level_quantity=Decimal(str(rq_raw)) if rq_raw else None,
            description=state.get(K.KEY_DESCRIPTION),
        )
        item = context.service_registry.item_service.create_item(company_id, cmd)
        state[K.KEY_ITEM_ID] = item.id

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        iid = state.get(K.KEY_ITEM_ID)
        if iid:
            return f"Item #{iid} created."
        return f"Create item {state.get(K.KEY_ITEM_NAME) or ''}".strip()
