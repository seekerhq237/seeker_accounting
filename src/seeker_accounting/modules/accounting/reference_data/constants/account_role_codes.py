from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountRoleDefinition:
    role_code: str
    label: str
    description: str


ACCOUNT_ROLE_DEFINITIONS: tuple[AccountRoleDefinition, ...] = (
    AccountRoleDefinition("ar_control", "AR Control", "Default receivables control account."),
    AccountRoleDefinition("ap_control", "AP Control", "Default payables control account."),
    AccountRoleDefinition("inventory_control", "Inventory Control", "Default inventory control account."),
    AccountRoleDefinition("cash_on_hand", "Cash On Hand", "Primary cash-on-hand account."),
    AccountRoleDefinition("petty_cash", "Petty Cash", "Primary petty cash account."),
    AccountRoleDefinition("bank_main", "Main Bank", "Primary bank settlement account."),
    AccountRoleDefinition(
        "sales_revenue_default",
        "Sales Revenue",
        "Default operating sales revenue account.",
    ),
    AccountRoleDefinition(
        "purchases_expense_default",
        "Purchases Expense",
        "Default operating purchases expense account.",
    ),
    AccountRoleDefinition(
        "payroll_payable",
        "Payroll Payable",
        "Default payroll liability account.",
    ),
    AccountRoleDefinition(
        "contract_revenue_default",
        "Contract Revenue",
        "Default contract revenue recognition account.",
    ),
    AccountRoleDefinition(
        "project_cost_default",
        "Project Cost",
        "Default project cost accumulation account.",
    ),
    AccountRoleDefinition(
        "project_wip_asset",
        "Project WIP Asset",
        "Work-in-progress asset account for projects.",
    ),
    AccountRoleDefinition(
        "project_billed_not_earned",
        "Project Billed Not Earned",
        "Liability for billed but not yet earned revenue.",
    ),
    AccountRoleDefinition(
        "project_retention_receivable",
        "Project Retention Receivable",
        "Receivable for retention amounts on projects.",
    ),
    AccountRoleDefinition(
        "project_deferred_revenue",
        "Project Deferred Revenue",
        "Deferred revenue account for projects.",
    ),
    AccountRoleDefinition(
        "project_overhead_recovery",
        "Project Overhead Recovery",
        "Account for recovering overhead on projects.",
    ),
)

ACCOUNT_ROLE_DEFINITION_BY_CODE = {
    definition.role_code: definition
    for definition in ACCOUNT_ROLE_DEFINITIONS
}

