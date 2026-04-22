from __future__ import annotations

from dataclasses import dataclass


OHADA_BALANCE_SHEET_VERSION = "ohada_balance_sheet_v1"

OHADA_BALANCE_MODE_DEBIT = "debit_balance"
OHADA_BALANCE_MODE_CREDIT = "credit_balance"
OHADA_BALANCE_MODE_LIABILITY_SIGNED = "signed_credit_minus_debit"


@dataclass(frozen=True, slots=True)
class OhadaBalanceSheetSelectorSpec:
    include_prefixes: tuple[str, ...]
    exclude_prefixes: tuple[str, ...] = ()
    include_exact_codes: tuple[str, ...] = ()
    exclude_exact_codes: tuple[str, ...] = ()
    balance_mode: str = OHADA_BALANCE_MODE_DEBIT
    contribution_kind_code: str = "balance"


@dataclass(frozen=True, slots=True)
class OhadaBalanceSheetLineSpec:
    code: str
    label: str
    side_code: str
    section_code: str
    section_title: str
    display_order: int
    row_kind_code: str
    reference_code: str | None = None
    selectors: tuple[OhadaBalanceSheetSelectorSpec, ...] = ()
    total_components: tuple[str, ...] = ()


def _gross(
    *prefixes: str,
    exclude: tuple[str, ...] = (),
    exact: tuple[str, ...] = (),
    exclude_exact: tuple[str, ...] = (),
) -> OhadaBalanceSheetSelectorSpec:
    return OhadaBalanceSheetSelectorSpec(
        include_prefixes=prefixes,
        exclude_prefixes=exclude,
        include_exact_codes=exact,
        exclude_exact_codes=exclude_exact,
        balance_mode=OHADA_BALANCE_MODE_DEBIT,
        contribution_kind_code="gross",
    )


def _contra(
    *prefixes: str,
    exclude: tuple[str, ...] = (),
    exact: tuple[str, ...] = (),
    exclude_exact: tuple[str, ...] = (),
) -> OhadaBalanceSheetSelectorSpec:
    return OhadaBalanceSheetSelectorSpec(
        include_prefixes=prefixes,
        exclude_prefixes=exclude,
        include_exact_codes=exact,
        exclude_exact_codes=exclude_exact,
        balance_mode=OHADA_BALANCE_MODE_CREDIT,
        contribution_kind_code="contra",
    )


def _liability(
    *prefixes: str,
    exclude: tuple[str, ...] = (),
    exact: tuple[str, ...] = (),
    exclude_exact: tuple[str, ...] = (),
) -> OhadaBalanceSheetSelectorSpec:
    return OhadaBalanceSheetSelectorSpec(
        include_prefixes=prefixes,
        exclude_prefixes=exclude,
        include_exact_codes=exact,
        exclude_exact_codes=exclude_exact,
        balance_mode=OHADA_BALANCE_MODE_LIABILITY_SIGNED,
        contribution_kind_code="balance",
    )


def _credit_only(
    *prefixes: str,
    exclude: tuple[str, ...] = (),
    exact: tuple[str, ...] = (),
    exclude_exact: tuple[str, ...] = (),
) -> OhadaBalanceSheetSelectorSpec:
    return OhadaBalanceSheetSelectorSpec(
        include_prefixes=prefixes,
        exclude_prefixes=exclude,
        include_exact_codes=exact,
        exclude_exact_codes=exclude_exact,
        balance_mode=OHADA_BALANCE_MODE_CREDIT,
        contribution_kind_code="balance",
    )


OHADA_BALANCE_SHEET_LINE_SPECS: tuple[OhadaBalanceSheetLineSpec, ...] = (
    OhadaBalanceSheetLineSpec("AD", "INTANGIBLE FIXED ASSETS", "assets", "fixed_assets", "Fixed Assets", 10, "section", "AD"),
    OhadaBalanceSheetLineSpec(
        "AE",
        "Research and development expenses",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        20,
        "line",
        "AE",
        selectors=(
            _gross("211", "2181", "2191"),
            _contra("2811", "2818", "2911", "2918", "2919", exclude_exact=("2818", "2918", "2919")),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AF",
        "Patent, license, software and similar rights",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        30,
        "line",
        "AF",
        selectors=(
            _gross("212", "213", "214", "2193"),
            _contra("2812", "2813", "2814", "2912", "2913", "2914", "2919", exclude_exact=("2919",)),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AG",
        "Goodwill and leasing rights",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        40,
        "line",
        "AG",
        selectors=(
            _gross("215", "216"),
            _contra("2815", "2816", "2915", "2916"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AH",
        "Other intangible assets",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        50,
        "line",
        "AH",
        selectors=(
            _gross("217", "218", "2198", exclude=("2181",)),
            _contra("2817", "2818", "2917", "2918", "2919", exclude_exact=("2818", "2918", "2919")),
        ),
    ),
    OhadaBalanceSheetLineSpec("AI", "TANGIBLE FIXED ASSETS", "assets", "fixed_assets", "Fixed Assets", 60, "section", "AI"),
    OhadaBalanceSheetLineSpec(
        "AJ",
        "Lands",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        70,
        "line",
        "AJ",
        selectors=(
            _gross("22"),
            _contra("282", "292"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AK",
        "Building",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        80,
        "line",
        "AK",
        selectors=(
            _gross("231", "232", "233", "237", "2391"),
            _contra("2831", "2832", "2833", "2837", "2931", "2932", "2933", "2937", "2939", exclude_exact=("2939",)),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AL",
        "Fittings, plants and assimilated",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        90,
        "line",
        "AL",
        selectors=(
            _gross("234", "235", "238", "2392", "2393"),
            _contra("2834", "2835", "2838", "2934", "2939", exclude_exact=("2939",)),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AM",
        "Equipments, furniture and biological assets",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        100,
        "line",
        "AM",
        selectors=(
            _gross("24", exclude=("245", "2495")),
            _contra("284", "294", exclude=("2845", "2945", "2949")),
            _contra(exact=("2949",)),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AN",
        "Transport equipments",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        110,
        "line",
        "AN",
        selectors=(
            _gross("245", "2495"),
            _contra("2845", "2945", "2949", exclude_exact=("2949",)),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AP",
        "Advances and payment on account of fixed assets",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        120,
        "line",
        "AP",
        selectors=(
            _gross("251", "252"),
            _contra("2951", "2952"),
        ),
    ),
    OhadaBalanceSheetLineSpec("AQ", "FINANCIAL FIXED ASSETS", "assets", "fixed_assets", "Fixed Assets", 130, "section", "AQ"),
    OhadaBalanceSheetLineSpec(
        "AR",
        "Participation certificates",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        140,
        "line",
        "AR",
        selectors=(
            _gross("26"),
            _contra("296"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AS",
        "Other financial fixed assets",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        150,
        "line",
        "AS",
        selectors=(
            _gross("27"),
            _contra("297"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "AZ",
        "TOTAL FIXED ASSETS (I)",
        "assets",
        "fixed_assets",
        "Fixed Assets",
        160,
        "total",
        "AZ",
        total_components=("AE", "AF", "AG", "AH", "AJ", "AK", "AL", "AM", "AN", "AP", "AR", "AS"),
    ),
    OhadaBalanceSheetLineSpec(
        "BA",
        "Current assets OOA",
        "assets",
        "current_assets",
        "Current Assets",
        170,
        "line",
        "BA",
        selectors=(
            _gross("485", "488"),
            _contra("498"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "BB",
        "Stock and in process",
        "assets",
        "current_assets",
        "Current Assets",
        180,
        "line",
        "BB",
        selectors=(
            _gross("31", "32", "3391", "34", "35", "36", "37", "38"),
            _contra("39"),
        ),
    ),
    OhadaBalanceSheetLineSpec("BG", "Debits and assimilated applications", "assets", "current_assets", "Current Assets", 190, "section", "BG"),
    OhadaBalanceSheetLineSpec(
        "BH",
        "Suppliers advances paid",
        "assets",
        "current_assets",
        "Current Assets",
        200,
        "line",
        "BH",
        selectors=(
            _gross("409"),
            _contra("490"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "BI",
        "Customers",
        "assets",
        "current_assets",
        "Current Assets",
        210,
        "line",
        "BI",
        selectors=(
            _gross("41", exclude=("419",)),
            _contra("491"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "BJ",
        "Other debts",
        "assets",
        "current_assets",
        "Current Assets",
        220,
        "line",
        "BJ",
        selectors=(
            _gross("42", "43", "44", "45", "46", "47", exclude=("478",)),
            _contra("492", "493", "494", "495", "496", "497"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "BK",
        "TOTAL CURRENT ASSETS (II)",
        "assets",
        "current_assets",
        "Current Assets",
        230,
        "total",
        "BK",
        total_components=("BA", "BB", "BH", "BI", "BJ"),
    ),
    OhadaBalanceSheetLineSpec("LIQUID_ASSETS_SECTION", "LIQUID ASSETS", "assets", "liquid_assets", "Liquid Assets", 240, "section"),
    OhadaBalanceSheetLineSpec(
        "BQ",
        "Investment securities",
        "assets",
        "liquid_assets",
        "Liquid Assets",
        250,
        "line",
        "BQ",
        selectors=(
            _gross("50"),
            _contra("590"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "BR",
        "Receivable",
        "assets",
        "liquid_assets",
        "Liquid Assets",
        260,
        "line",
        "BR",
        selectors=(
            _gross("51"),
            _contra("591"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "BS",
        "Bank, giro bank, cash and assimilated",
        "assets",
        "liquid_assets",
        "Liquid Assets",
        270,
        "line",
        "BS",
        selectors=(
            _gross("52", "53", "54", "55", "57", "581", "582"),
            _contra("592", "593", "594"),
        ),
    ),
    OhadaBalanceSheetLineSpec(
        "BT",
        "TOTAL LIQUID ASSETS (III)",
        "assets",
        "liquid_assets",
        "Liquid Assets",
        280,
        "total",
        "BT",
        total_components=("BQ", "BR", "BS"),
    ),
    OhadaBalanceSheetLineSpec(
        "BU",
        "Assets conversion variance (IV)",
        "assets",
        "liquid_assets",
        "Liquid Assets",
        290,
        "line",
        "BU",
        selectors=(_gross("478"),),
    ),
    OhadaBalanceSheetLineSpec(
        "BZ",
        "GENERAL TOTAL (I+II+III+IV)",
        "assets",
        "liquid_assets",
        "Liquid Assets",
        300,
        "total",
        "BZ",
        total_components=("AZ", "BK", "BT", "BU"),
    ),
    OhadaBalanceSheetLineSpec("CA", "SHAREHOLDERS EQUITY AND ASSIMILATED SOURCES", "liabilities", "equity", "Equity", 310, "section", "CA"),
    OhadaBalanceSheetLineSpec("CB", "Shareholders subscribed, uncalled up capital", "liabilities", "equity", "Equity", 320, "line", "CB", selectors=(_liability("101", "102", "103", "104"),)),
    OhadaBalanceSheetLineSpec("CD", "Capital", "liabilities", "equity", "Equity", 330, "line", "CD", selectors=(_liability("109"),)),
    OhadaBalanceSheetLineSpec("CE", "Revaluation related to social capital", "liabilities", "equity", "Equity", 340, "line", "CE", selectors=(_liability("105"),)),
    OhadaBalanceSheetLineSpec("CF", "Unavailable reserves", "liabilities", "equity", "Equity", 350, "line", "CF", selectors=(_liability("106"),)),
    OhadaBalanceSheetLineSpec("CG", "Optional reserves", "liabilities", "equity", "Equity", 360, "line", "CG", selectors=(_liability("111", "112", "113", "118"),)),
    OhadaBalanceSheetLineSpec("CH", "Brought forward (or C/F) (- or +)", "liabilities", "equity", "Equity", 370, "line", "CH", selectors=(_liability("12"),)),
    OhadaBalanceSheetLineSpec("CI", "RESULT PROFIT OR LOSS OF THE YEAR", "liabilities", "equity", "Equity", 380, "line", "CI", selectors=(_liability("13"),)),
    OhadaBalanceSheetLineSpec("CL", "Investment subsidies", "liabilities", "equity", "Equity", 390, "line", "CL", selectors=(_liability("14"),)),
    OhadaBalanceSheetLineSpec("CM", "Regulated provisions and assimilated fund", "liabilities", "equity", "Equity", 400, "line", "CM", selectors=(_liability("15"),)),
    OhadaBalanceSheetLineSpec(
        "CP",
        "TOTAL SHAREHOLDERS EQUITY AND ASSIMILATED SOURCES (I)",
        "liabilities",
        "equity",
        "Equity",
        410,
        "total",
        "CP",
        total_components=("CB", "CD", "CE", "CF", "CG", "CH", "CI", "CL", "CM"),
    ),
    OhadaBalanceSheetLineSpec("DA", "FINANCIAL DEBTS AND ASSIMILATED SOURCES", "liabilities", "non_current_liabilities", "Non-Current Liabilities", 420, "section", "DA"),
    OhadaBalanceSheetLineSpec("DB", "Borrowings and various financial debts", "liabilities", "non_current_liabilities", "Non-Current Liabilities", 430, "line", "DB", selectors=(_liability("16", "181", "182", "183", "184"),)),
    OhadaBalanceSheetLineSpec("DC", "Renting and leasing obligations", "liabilities", "non_current_liabilities", "Non-Current Liabilities", 440, "line", "DC", selectors=(_liability("17"),)),
    OhadaBalanceSheetLineSpec("DD", "Provisions for risks and expenses", "liabilities", "non_current_liabilities", "Non-Current Liabilities", 450, "line", "DD", selectors=(_liability("19"),)),
    OhadaBalanceSheetLineSpec(
        "DF",
        "TOTAL FINANCIAL DEBTS AND ASSIMILATED RESOURCES (II)",
        "liabilities",
        "non_current_liabilities",
        "Non-Current Liabilities",
        460,
        "total",
        "DF",
        total_components=("DB", "DC", "DD"),
    ),
    OhadaBalanceSheetLineSpec(
        "DURABLE_RESOURCES_TOTAL",
        "TOTAL DURABLE RESOURCES (I+II)",
        "liabilities",
        "non_current_liabilities",
        "Non-Current Liabilities",
        470,
        "total",
        total_components=("CP", "DF"),
    ),
    OhadaBalanceSheetLineSpec("DH", "CURRENT LIABILITIES", "liabilities", "current_liabilities", "Current Liabilities", 480, "section", "DH"),
    OhadaBalanceSheetLineSpec("DI", "Current debts OOA", "liabilities", "current_liabilities", "Current Liabilities", 490, "line", "DI", selectors=(_credit_only("481", "482", "484", "4908"),)),
    OhadaBalanceSheetLineSpec("DJ", "Customers advances on account received", "liabilities", "current_liabilities", "Current Liabilities", 500, "line", "DJ", selectors=(_credit_only("419"),)),
    OhadaBalanceSheetLineSpec("DK", "Operating suppliers", "liabilities", "current_liabilities", "Current Liabilities", 510, "line", "DK", selectors=(_credit_only("40"),)),
    OhadaBalanceSheetLineSpec("DL", "Fiscal and social debts", "liabilities", "current_liabilities", "Current Liabilities", 520, "line", "DL", selectors=(_credit_only("42", "43", "44", exclude=("419",)),)),
    OhadaBalanceSheetLineSpec("DM", "Other debts", "liabilities", "current_liabilities", "Current Liabilities", 530, "line", "DM", selectors=(_credit_only("185", "41", "45", "46", "47", exclude=("419", "479")),)),
    OhadaBalanceSheetLineSpec("DN", "Provisioned risks at short term", "liabilities", "current_liabilities", "Current Liabilities", 540, "line", "DN", selectors=(_credit_only("499", "599", exclude=("4908",)),)),
    OhadaBalanceSheetLineSpec(
        "DP",
        "TOTAL LIABILITIES (III)",
        "liabilities",
        "current_liabilities",
        "Current Liabilities",
        550,
        "total",
        "DP",
        total_components=("DI", "DJ", "DK", "DL", "DM", "DN"),
    ),
    OhadaBalanceSheetLineSpec("DQ", "Bank, discount credit", "liabilities", "cash_liabilities", "Cash Liabilities", 560, "line", "DQ", selectors=(_credit_only("564", "565"),)),
    OhadaBalanceSheetLineSpec("DR", "Bank, financial establishments treasury credits", "liabilities", "cash_liabilities", "Cash Liabilities", 570, "line", "DR", selectors=(_credit_only("52", "53", "56", "566", exclude=("564", "565")),)),
    OhadaBalanceSheetLineSpec(
        "DT",
        "TOTAL CASH LIABILITIES (IV)",
        "liabilities",
        "cash_liabilities",
        "Cash Liabilities",
        580,
        "total",
        "DT",
        total_components=("DQ", "DR"),
    ),
    OhadaBalanceSheetLineSpec("DU", "Liabilities conversion variance (V)", "liabilities", "cash_liabilities", "Cash Liabilities", 590, "line", "DU", selectors=(_credit_only("479"),)),
    OhadaBalanceSheetLineSpec(
        "DZ",
        "GENERAL TOTAL (I+II+III+IV+V)",
        "liabilities",
        "cash_liabilities",
        "Cash Liabilities",
        600,
        "total",
        "DZ",
        total_components=("CP", "DF", "DP", "DT", "DU"),
    ),
)

OHADA_BALANCE_SHEET_SPEC_BY_CODE = {spec.code: spec for spec in OHADA_BALANCE_SHEET_LINE_SPECS}
OHADA_BALANCE_SHEET_BASE_LINE_SPECS = tuple(spec for spec in OHADA_BALANCE_SHEET_LINE_SPECS if spec.selectors)
OHADA_BALANCE_SHEET_TOTAL_LINE_SPECS = tuple(spec for spec in OHADA_BALANCE_SHEET_LINE_SPECS if spec.total_components)
OHADA_BALANCE_SHEET_ASSET_LINES = tuple(spec for spec in OHADA_BALANCE_SHEET_LINE_SPECS if spec.side_code == "assets")
OHADA_BALANCE_SHEET_LIABILITY_LINES = tuple(spec for spec in OHADA_BALANCE_SHEET_LINE_SPECS if spec.side_code == "liabilities")
OHADA_BALANCE_SHEET_ALL_PREFIXES = tuple(
    prefix
    for spec in OHADA_BALANCE_SHEET_BASE_LINE_SPECS
    for selector in spec.selectors
    for prefix in selector.include_prefixes
) + tuple(
    code
    for spec in OHADA_BALANCE_SHEET_BASE_LINE_SPECS
    for selector in spec.selectors
    for code in selector.include_exact_codes
)
