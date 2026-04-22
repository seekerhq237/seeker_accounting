from __future__ import annotations

from dataclasses import dataclass

from seeker_accounting.modules.accounting.reference_data.models.account_class import AccountClass
from seeker_accounting.modules.accounting.reference_data.models.account_type import AccountType
from seeker_accounting.modules.accounting.reference_data.repositories.account_class_repository import (
    AccountClassRepository,
)
from seeker_accounting.modules.accounting.reference_data.repositories.account_type_repository import (
    AccountTypeRepository,
)


@dataclass(frozen=True, slots=True)
class AccountClassSeed:
    code: str
    name: str
    display_order: int


@dataclass(frozen=True, slots=True)
class AccountTypeSeed:
    code: str
    name: str
    normal_balance: str
    financial_statement_section_code: str


ACCOUNT_CLASS_SEEDS: tuple[AccountClassSeed, ...] = (
    AccountClassSeed("1", "Permanent Resources", 1),
    AccountClassSeed("2", "Non-Current Assets", 2),
    AccountClassSeed("3", "Inventory", 3),
    AccountClassSeed("4", "Third Parties", 4),
    AccountClassSeed("5", "Treasury", 5),
    AccountClassSeed("6", "Ordinary Activity Expenses", 6),
    AccountClassSeed("7", "Ordinary Activity Revenues", 7),
    AccountClassSeed("8", "Off Ordinary Activity Revenues and Expenses", 8),
    AccountClassSeed("9", "Contingency and Management Accounts", 9),
)

ACCOUNT_TYPE_SEEDS: tuple[AccountTypeSeed, ...] = (
    AccountTypeSeed("equity", "Equity", "CREDIT", "EQUITY"),
    AccountTypeSeed("noncurrent_liability", "Non-Current Liability", "CREDIT", "LIABILITY"),
    AccountTypeSeed("noncurrent_asset", "Non-Current Asset", "DEBIT", "ASSET"),
    AccountTypeSeed("contra_noncurrent_asset", "Contra Non-Current Asset", "CREDIT", "ASSET"),
    AccountTypeSeed("inventory_asset", "Inventory Asset", "DEBIT", "ASSET"),
    AccountTypeSeed("contra_inventory_asset", "Contra Inventory Asset", "CREDIT", "ASSET"),
    AccountTypeSeed("third_party", "Third Party", "DEBIT", "ASSET_LIABILITY"),
    AccountTypeSeed("contra_third_party", "Contra Third Party", "CREDIT", "ASSET_LIABILITY"),
    AccountTypeSeed("treasury_asset", "Treasury Asset", "DEBIT", "ASSET"),
    AccountTypeSeed("contra_treasury_asset", "Contra Treasury Asset", "CREDIT", "ASSET"),
    AccountTypeSeed("expense", "Expense", "DEBIT", "EXPENSE"),
    AccountTypeSeed("revenue", "Revenue", "CREDIT", "REVENUE"),
    AccountTypeSeed("other_expense", "Other Expense", "DEBIT", "EXPENSE"),
    AccountTypeSeed("other_revenue", "Other Revenue", "CREDIT", "REVENUE"),
    AccountTypeSeed("contingency_management", "Contingency And Management", "DEBIT", "OFF_BALANCE"),
)

ACCOUNT_CLASS_NAME_BY_CODE = {
    seed.code: seed.name
    for seed in ACCOUNT_CLASS_SEEDS
}

ACCOUNT_TYPE_SEED_BY_CODE = {
    seed.code: seed
    for seed in ACCOUNT_TYPE_SEEDS
}


def ensure_global_chart_reference_seed(
    account_class_repository: AccountClassRepository,
    account_type_repository: AccountTypeRepository,
) -> tuple[int, int]:
    inserted_account_class_count = 0
    inserted_account_type_count = 0

    for seed in ACCOUNT_CLASS_SEEDS:
        if account_class_repository.get_by_code(seed.code) is not None:
            continue
        account_class_repository.add(
            AccountClass(
                code=seed.code,
                name=seed.name,
                display_order=seed.display_order,
                is_active=True,
            )
        )
        inserted_account_class_count += 1

    for seed in ACCOUNT_TYPE_SEEDS:
        if account_type_repository.get_by_code(seed.code) is not None:
            continue
        account_type_repository.add(
            AccountType(
                code=seed.code,
                name=seed.name,
                normal_balance=seed.normal_balance,
                financial_statement_section_code=seed.financial_statement_section_code,
                is_active=True,
            )
        )
        inserted_account_type_count += 1

    return inserted_account_class_count, inserted_account_type_count
