from __future__ import annotations

from dataclasses import dataclass


IAS_BALANCE_SHEET_VERSION = "ias_balance_sheet_v1"

IAS_BALANCE_MODE_ASSET_SIGNED = "asset_signed"
IAS_BALANCE_MODE_LIABILITY_SIGNED = "liability_signed"
IAS_BALANCE_MODE_DEBIT = "debit_balance"
IAS_BALANCE_MODE_CREDIT = "credit_balance"

IAS_BALANCE_SHEET_RELEVANT_CLASS_CODES = {"1", "2", "3", "4", "5"}
IAS_BALANCE_SHEET_RELEVANT_SECTION_CODES = {"ASSET", "LIABILITY", "EQUITY", "ASSET_LIABILITY"}


@dataclass(frozen=True, slots=True)
class IasBalanceSheetSelectorSpec:
    include_prefixes: tuple[str, ...]
    exclude_prefixes: tuple[str, ...] = ()
    amount_mode: str = IAS_BALANCE_MODE_ASSET_SIGNED
    contribution_kind_code: str = "balance"


@dataclass(frozen=True, slots=True)
class IasBalanceSheetLineSpec:
    code: str
    label: str
    display_order: int
    row_kind_code: str
    parent_code: str | None = None
    selectors: tuple[IasBalanceSheetSelectorSpec, ...] = ()
    aggregation_components: tuple[str, ...] = ()
    formula_components: tuple[str, ...] = ()
    is_classification_target: bool = False

    @property
    def is_formula(self) -> bool:
        return bool(self.formula_components)


def _asset(*prefixes: str, exclude: tuple[str, ...] = ()) -> IasBalanceSheetSelectorSpec:
    return IasBalanceSheetSelectorSpec(prefixes, exclude, IAS_BALANCE_MODE_ASSET_SIGNED)


def _liability(*prefixes: str, exclude: tuple[str, ...] = ()) -> IasBalanceSheetSelectorSpec:
    return IasBalanceSheetSelectorSpec(prefixes, exclude, IAS_BALANCE_MODE_LIABILITY_SIGNED)


def _debit(*prefixes: str, exclude: tuple[str, ...] = ()) -> IasBalanceSheetSelectorSpec:
    return IasBalanceSheetSelectorSpec(prefixes, exclude, IAS_BALANCE_MODE_DEBIT)


def _credit(*prefixes: str, exclude: tuple[str, ...] = ()) -> IasBalanceSheetSelectorSpec:
    return IasBalanceSheetSelectorSpec(prefixes, exclude, IAS_BALANCE_MODE_CREDIT)


IAS_BALANCE_SHEET_LINE_SPECS: tuple[IasBalanceSheetLineSpec, ...] = (
    IasBalanceSheetLineSpec("ASSETS", "ASSETS", 10, "section"),
    IasBalanceSheetLineSpec(
        "NON_CURRENT_ASSETS",
        "Non-current assets",
        20,
        "group",
        parent_code="ASSETS",
        aggregation_components=(
            "PPE",
            "RIGHT_OF_USE_ASSETS",
            "INVESTMENT_PROPERTY",
            "INTANGIBLE_ASSETS",
            "FINANCIAL_ASSETS_NON_CURRENT",
            "DEFERRED_TAX_ASSETS",
            "OTHER_NON_CURRENT_ASSETS",
        ),
    ),
    IasBalanceSheetLineSpec(
        "PPE",
        "Property, plant and equipment",
        30,
        "line",
        parent_code="NON_CURRENT_ASSETS",
        selectors=(_asset("22", "23", "24", "25", "282", "283", "284", "292", "293", "294", "295"),),
        is_classification_target=True,
    ),
    IasBalanceSheetLineSpec("RIGHT_OF_USE_ASSETS", "Right-of-use assets", 40, "line", "NON_CURRENT_ASSETS", is_classification_target=True),
    IasBalanceSheetLineSpec("INVESTMENT_PROPERTY", "Investment property", 50, "line", "NON_CURRENT_ASSETS", is_classification_target=True),
    IasBalanceSheetLineSpec(
        "INTANGIBLE_ASSETS",
        "Intangible assets",
        60,
        "line",
        parent_code="NON_CURRENT_ASSETS",
        selectors=(_asset("21", "281", "291"),),
        is_classification_target=True,
    ),
    IasBalanceSheetLineSpec(
        "FINANCIAL_ASSETS_NON_CURRENT",
        "Financial assets (non-current)",
        70,
        "line",
        parent_code="NON_CURRENT_ASSETS",
        selectors=(_asset("26", "27", "296", "297"),),
        is_classification_target=True,
    ),
    IasBalanceSheetLineSpec("DEFERRED_TAX_ASSETS", "Deferred tax assets", 80, "line", "NON_CURRENT_ASSETS", is_classification_target=True),
    IasBalanceSheetLineSpec("OTHER_NON_CURRENT_ASSETS", "Other non-current assets", 90, "line", "NON_CURRENT_ASSETS", is_classification_target=True),
    IasBalanceSheetLineSpec("TOTAL_NON_CURRENT_ASSETS", "Total non-current assets", 100, "formula", "ASSETS", formula_components=("NON_CURRENT_ASSETS",)),
    IasBalanceSheetLineSpec(
        "CURRENT_ASSETS",
        "Current assets",
        110,
        "group",
        parent_code="ASSETS",
        aggregation_components=(
            "INVENTORIES",
            "TRADE_OTHER_RECEIVABLES",
            "CURRENT_TAX_ASSETS",
            "CASH_EQUIVALENTS",
            "OTHER_CURRENT_ASSETS",
        ),
    ),
    IasBalanceSheetLineSpec(
        "INVENTORIES",
        "Inventories",
        120,
        "line",
        parent_code="CURRENT_ASSETS",
        selectors=(_asset("31", "32", "33", "34", "35", "36", "37", "38", "39"),),
        is_classification_target=True,
    ),
    IasBalanceSheetLineSpec(
        "TRADE_OTHER_RECEIVABLES",
        "Trade and other receivables",
        130,
        "line",
        parent_code="CURRENT_ASSETS",
        selectors=(
            _debit("40", "41", "42", "43", "45", "46", "47", "48", exclude=("44", "478", "479", "485", "488")),
            _asset("490", "491", "492", "493", "494", "495", "496", "497", exclude=("4908",)),
        ),
        is_classification_target=True,
    ),
    IasBalanceSheetLineSpec(
        "CURRENT_TAX_ASSETS",
        "Current tax assets",
        140,
        "line",
        parent_code="CURRENT_ASSETS",
        selectors=(_debit("44"),),
        is_classification_target=True,
    ),
    IasBalanceSheetLineSpec(
        "CASH_EQUIVALENTS",
        "Cash and cash equivalents",
        150,
        "line",
        parent_code="CURRENT_ASSETS",
        selectors=(
            _debit("50", "51", "52", "53", "54", "55", "56", "57", "58"),
            _asset("590", "591", "592", "593", "594"),
        ),
        is_classification_target=True,
    ),
    IasBalanceSheetLineSpec(
        "OTHER_CURRENT_ASSETS",
        "Other current assets",
        160,
        "line",
        parent_code="CURRENT_ASSETS",
        selectors=(_debit("478", "485", "488"), _asset("498")),
        is_classification_target=True,
    ),
    IasBalanceSheetLineSpec("TOTAL_CURRENT_ASSETS", "Total current assets", 170, "formula", "ASSETS", formula_components=("CURRENT_ASSETS",)),
    IasBalanceSheetLineSpec("TOTAL_ASSETS", "TOTAL ASSETS", 180, "formula", formula_components=("TOTAL_NON_CURRENT_ASSETS", "TOTAL_CURRENT_ASSETS")),
    IasBalanceSheetLineSpec("EQUITY_AND_LIABILITIES", "EQUITY AND LIABILITIES", 190, "section"),
    IasBalanceSheetLineSpec(
        "EQUITY",
        "Equity",
        200,
        "group",
        parent_code="EQUITY_AND_LIABILITIES",
        aggregation_components=(
            "SHARE_CAPITAL",
            "SHARE_PREMIUM",
            "OTHER_RESERVES",
            "RETAINED_EARNINGS",
            "CURRENT_YEAR_RESULT",
        ),
    ),
    IasBalanceSheetLineSpec("SHARE_CAPITAL", "Share capital / issued capital", 210, "line", "EQUITY", selectors=(_liability("101", "102", "103", "104", "109"),), is_classification_target=True),
    IasBalanceSheetLineSpec("SHARE_PREMIUM", "Share premium or similar capital reserves", 220, "line", "EQUITY", selectors=(_liability("105"),), is_classification_target=True),
    IasBalanceSheetLineSpec("OTHER_RESERVES", "Other reserves", 230, "line", "EQUITY", selectors=(_liability("106", "111", "112", "113", "13", "14"),), is_classification_target=True),
    IasBalanceSheetLineSpec("RETAINED_EARNINGS", "Retained earnings / brought forward", 240, "line", "EQUITY", selectors=(_liability("118"),), is_classification_target=True),
    IasBalanceSheetLineSpec("CURRENT_YEAR_RESULT", "Current year result", 250, "line", "EQUITY", selectors=(_liability("12"),), is_classification_target=True),
    IasBalanceSheetLineSpec("TOTAL_EQUITY", "Total equity", 260, "formula", "EQUITY_AND_LIABILITIES", formula_components=("EQUITY",)),
    IasBalanceSheetLineSpec(
        "NON_CURRENT_LIABILITIES",
        "Non-current liabilities",
        270,
        "group",
        parent_code="EQUITY_AND_LIABILITIES",
        aggregation_components=(
            "NCL_BORROWINGS",
            "NCL_LEASE_LIABILITIES",
            "NCL_DEFERRED_TAX",
            "NCL_PROVISIONS",
            "NCL_OTHER",
        ),
    ),
    IasBalanceSheetLineSpec("NCL_BORROWINGS", "Borrowings", 280, "line", "NON_CURRENT_LIABILITIES", selectors=(_liability("16", "181", "182", "183", "184"),), is_classification_target=True),
    IasBalanceSheetLineSpec("NCL_LEASE_LIABILITIES", "Lease liabilities", 290, "line", "NON_CURRENT_LIABILITIES", selectors=(_liability("17"),), is_classification_target=True),
    IasBalanceSheetLineSpec("NCL_DEFERRED_TAX", "Deferred tax liabilities", 300, "line", "NON_CURRENT_LIABILITIES", is_classification_target=True),
    IasBalanceSheetLineSpec("NCL_PROVISIONS", "Provisions", 310, "line", "NON_CURRENT_LIABILITIES", selectors=(_liability("15", "19"),), is_classification_target=True),
    IasBalanceSheetLineSpec("NCL_OTHER", "Other non-current liabilities", 320, "line", "NON_CURRENT_LIABILITIES", selectors=(_liability("18", exclude=("181", "182", "183", "184", "185")),), is_classification_target=True),
    IasBalanceSheetLineSpec("TOTAL_NON_CURRENT_LIABILITIES", "Total non-current liabilities", 330, "formula", "EQUITY_AND_LIABILITIES", formula_components=("NON_CURRENT_LIABILITIES",)),
    IasBalanceSheetLineSpec(
        "CURRENT_LIABILITIES",
        "Current liabilities",
        340,
        "group",
        parent_code="EQUITY_AND_LIABILITIES",
        aggregation_components=(
            "CL_TRADE_OTHER_PAYABLES",
            "CL_CURRENT_TAX",
            "CL_BORROWINGS",
            "CL_LEASE_LIABILITIES",
            "CL_PROVISIONS",
            "CL_OTHER",
        ),
    ),
    IasBalanceSheetLineSpec("CL_TRADE_OTHER_PAYABLES", "Trade and other payables", 350, "line", "CURRENT_LIABILITIES", selectors=(_credit("40", "41", "42", "43", "45", "46", "47", "48", exclude=("44", "478", "479", "481", "482", "484")),), is_classification_target=True),
    IasBalanceSheetLineSpec("CL_CURRENT_TAX", "Current tax liabilities", 360, "line", "CURRENT_LIABILITIES", selectors=(_credit("44"),), is_classification_target=True),
    IasBalanceSheetLineSpec("CL_BORROWINGS", "Borrowings", 370, "line", "CURRENT_LIABILITIES", selectors=(_credit("52", "53", "56", exclude=("564", "565")), _credit("564", "565")), is_classification_target=True),
    IasBalanceSheetLineSpec("CL_LEASE_LIABILITIES", "Lease liabilities", 380, "line", "CURRENT_LIABILITIES", is_classification_target=True),
    IasBalanceSheetLineSpec("CL_PROVISIONS", "Provisions", 390, "line", "CURRENT_LIABILITIES", selectors=(_credit("499", "599"),), is_classification_target=True),
    IasBalanceSheetLineSpec("CL_OTHER", "Other current liabilities", 400, "line", "CURRENT_LIABILITIES", selectors=(_credit("185", "479", "481", "482", "484", "4908"),), is_classification_target=True),
    IasBalanceSheetLineSpec("TOTAL_CURRENT_LIABILITIES", "Total current liabilities", 410, "formula", "EQUITY_AND_LIABILITIES", formula_components=("CURRENT_LIABILITIES",)),
    IasBalanceSheetLineSpec("TOTAL_EQUITY_AND_LIABILITIES", "TOTAL EQUITY AND LIABILITIES", 420, "formula", formula_components=("TOTAL_EQUITY", "TOTAL_NON_CURRENT_LIABILITIES", "TOTAL_CURRENT_LIABILITIES")),
)

IAS_BALANCE_SHEET_SPEC_BY_CODE = {spec.code: spec for spec in IAS_BALANCE_SHEET_LINE_SPECS}
