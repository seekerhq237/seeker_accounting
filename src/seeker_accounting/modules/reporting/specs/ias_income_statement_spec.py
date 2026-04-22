from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


IAS_INCOME_STATEMENT_PROFILE_CODE = "ias_ifrs_income_statement_v1"
IAS_SIGN_BEHAVIOR_NORMAL = "normal"
IAS_SIGN_BEHAVIOR_INVERTED = "inverted"

IAS_RELEVANT_ACCOUNT_TYPE_SECTION_CODES = {"REVENUE", "EXPENSE"}
IAS_RELEVANT_ACCOUNT_CLASS_CODES = {"6", "7", "8"}


@dataclass(frozen=True, slots=True)
class IasIncomeStatementTemplateSpec:
    template_code: str
    template_title: str
    description: str
    standard_note: str
    display_order: int
    row_height: int
    section_background: str
    subtotal_background: str
    statement_background: str
    amount_font_size: int
    label_font_size: int


@dataclass(frozen=True, slots=True)
class IasIncomeStatementSectionSpec:
    section_code: str
    section_label: str
    display_order: int
    row_kind_code: str
    parent_section_code: str | None = None
    is_mapping_target: bool = False
    aggregation_components: tuple[str, ...] = ()
    formula_components: tuple[str, ...] = ()

    @property
    def is_formula(self) -> bool:
        return bool(self.formula_components)


IAS_TEMPLATE_SPECS: tuple[IasIncomeStatementTemplateSpec, ...] = (
    IasIncomeStatementTemplateSpec(
        template_code="corporate_classic",
        template_title="Corporate Classic",
        description=(
            "Formal statutory presentation with restrained spacing and a conservative "
            "hierarchy suited to board packs and official review."
        ),
        standard_note="IAS / IFRS",
        display_order=10,
        row_height=28,
        section_background="#F3F4F6",
        subtotal_background="#E5E7EB",
        statement_background="#FFFFFF",
        amount_font_size=11,
        label_font_size=10,
    ),
    IasIncomeStatementTemplateSpec(
        template_code="board_presentation",
        template_title="Board Presentation",
        description=(
            "Clearer spacing and stronger subtotal emphasis for board and management "
            "review of profitability levels."
        ),
        standard_note="IAS / IFRS",
        display_order=20,
        row_height=26,
        section_background="#EEF2F7",
        subtotal_background="#DDE5EF",
        statement_background="#FFFFFF",
        amount_font_size=11,
        label_font_size=10,
    ),
    IasIncomeStatementTemplateSpec(
        template_code="executive_presentation",
        template_title="Executive Presentation",
        description=(
            "Premium hierarchy with refined spacing and cleaner grouping while remaining "
            "serious accounting software, not decorative BI."
        ),
        standard_note="IAS / IFRS",
        display_order=30,
        row_height=32,
        section_background="#EAF0FF",
        subtotal_background="#DCE7F7",
        statement_background="#FCFCFD",
        amount_font_size=12,
        label_font_size=11,
    ),
)


IAS_SECTION_SPECS: tuple[IasIncomeStatementSectionSpec, ...] = (
    IasIncomeStatementSectionSpec(
        section_code="REV",
        section_label="Revenue",
        display_order=10,
        row_kind_code="section",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="COS",
        section_label="Cost of Sales",
        display_order=20,
        row_kind_code="section",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="GROSS_PROFIT",
        section_label="Gross Profit",
        display_order=30,
        row_kind_code="formula",
        formula_components=("REV", "COS"),
    ),
    IasIncomeStatementSectionSpec(
        section_code="OPERATING_EXPENSES",
        section_label="Operating Expenses",
        display_order=40,
        row_kind_code="group",
        aggregation_components=("OPEX_SELLING", "OPEX_ADMIN", "OPEX_OTHER", "OINC_OTHER"),
    ),
    IasIncomeStatementSectionSpec(
        section_code="OPEX_SELLING",
        section_label="Selling and Distribution Expenses",
        display_order=50,
        row_kind_code="subsection",
        parent_section_code="OPERATING_EXPENSES",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="OPEX_ADMIN",
        section_label="Administrative Expenses",
        display_order=60,
        row_kind_code="subsection",
        parent_section_code="OPERATING_EXPENSES",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="OPEX_OTHER",
        section_label="Other Operating Expenses",
        display_order=70,
        row_kind_code="subsection",
        parent_section_code="OPERATING_EXPENSES",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="OINC_OTHER",
        section_label="Other Operating Income",
        display_order=80,
        row_kind_code="subsection",
        parent_section_code="OPERATING_EXPENSES",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="OPERATING_PROFIT",
        section_label="Operating Profit",
        display_order=90,
        row_kind_code="formula",
        formula_components=("GROSS_PROFIT", "OPERATING_EXPENSES"),
    ),
    IasIncomeStatementSectionSpec(
        section_code="FIN_INCOME",
        section_label="Finance Income",
        display_order=100,
        row_kind_code="section",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="FIN_COSTS",
        section_label="Finance Costs",
        display_order=110,
        row_kind_code="section",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="PROFIT_BEFORE_TAX",
        section_label="Profit Before Tax",
        display_order=120,
        row_kind_code="formula",
        formula_components=("OPERATING_PROFIT", "FIN_INCOME", "FIN_COSTS"),
    ),
    IasIncomeStatementSectionSpec(
        section_code="INCOME_TAX",
        section_label="Income Tax Expense",
        display_order=130,
        row_kind_code="section",
        is_mapping_target=True,
    ),
    IasIncomeStatementSectionSpec(
        section_code="PROFIT_FOR_PERIOD",
        section_label="Profit for the Period",
        display_order=140,
        row_kind_code="formula",
        formula_components=("PROFIT_BEFORE_TAX", "INCOME_TAX"),
    ),
)


IAS_SECTION_SPEC_BY_CODE = {spec.section_code: spec for spec in IAS_SECTION_SPECS}
IAS_TEMPLATE_SPEC_BY_CODE = {spec.template_code: spec for spec in IAS_TEMPLATE_SPECS}
IAS_MAPPING_TARGET_CODES = tuple(
    spec.section_code for spec in IAS_SECTION_SPECS if spec.is_mapping_target
)
IAS_FORMULA_SECTION_CODES = tuple(
    spec.section_code for spec in IAS_SECTION_SPECS if spec.is_formula
)
IAS_VISIBLE_STATEMENT_CODES = tuple(spec.section_code for spec in IAS_SECTION_SPECS)


def normalize_sign_behavior_code(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized == IAS_SIGN_BEHAVIOR_INVERTED:
        return IAS_SIGN_BEHAVIOR_INVERTED
    return IAS_SIGN_BEHAVIOR_NORMAL


def suggest_default_sign_behavior(
    *,
    normal_balance: str | None,
    account_type_section_code: str | None,
) -> str:
    section_code = (account_type_section_code or "").strip().upper()
    balance_code = (normal_balance or "").strip().upper()

    if section_code in {"REVENUE", "OTHER_REVENUE"}:
        return IAS_SIGN_BEHAVIOR_NORMAL
    if section_code in {"EXPENSE", "OTHER_EXPENSE"}:
        return IAS_SIGN_BEHAVIOR_INVERTED
    if balance_code == "DEBIT":
        return IAS_SIGN_BEHAVIOR_INVERTED
    return IAS_SIGN_BEHAVIOR_NORMAL


def is_relevant_income_statement_account(
    *,
    account_class_code: str | None,
    account_type_section_code: str | None,
    account_code: str,
) -> bool:
    normalized_code = (account_code or "").strip()
    if account_class_code in IAS_RELEVANT_ACCOUNT_CLASS_CODES:
        return True
    if (account_type_section_code or "").strip().upper() in IAS_RELEVANT_ACCOUNT_TYPE_SECTION_CODES:
        return True
    return normalized_code.startswith(("6", "7", "8"))


def compute_natural_amount(
    *,
    total_debit: Decimal,
    total_credit: Decimal,
    normal_balance: str | None,
) -> Decimal:
    balance_code = (normal_balance or "").strip().upper()
    if balance_code == "DEBIT":
        return (total_debit - total_credit).quantize(Decimal("0.01"))
    return (total_credit - total_debit).quantize(Decimal("0.01"))


def apply_sign_behavior(natural_amount: Decimal, sign_behavior_code: str | None) -> Decimal:
    if normalize_sign_behavior_code(sign_behavior_code) == IAS_SIGN_BEHAVIOR_INVERTED:
        return (-natural_amount).quantize(Decimal("0.01"))
    return natural_amount.quantize(Decimal("0.01"))

