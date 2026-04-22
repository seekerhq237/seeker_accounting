from __future__ import annotations

from dataclasses import dataclass


OHADA_INCOME_STATEMENT_VERSION = "ohada_income_statement_v1"


@dataclass(frozen=True, slots=True)
class OhadaIncomeStatementLineSpec:
    code: str
    label: str
    section_code: str
    section_title: str
    display_order: int
    prefixes: tuple[str, ...] = ()
    formula_components: tuple[str, ...] = ()

    @property
    def is_formula(self) -> bool:
        return bool(self.formula_components)


OHADA_BASE_LINE_SPECS: tuple[OhadaIncomeStatementLineSpec, ...] = (
    OhadaIncomeStatementLineSpec("TA", "Sales of goods", "commercial_margin", "Commercial Margin", 10, ("701",)),
    OhadaIncomeStatementLineSpec("RA", "Purchases of goods", "commercial_margin", "Commercial Margin", 20, ("601",)),
    OhadaIncomeStatementLineSpec(
        "RB", "Variation of stock of goods", "commercial_margin", "Commercial Margin", 30, ("6031",)
    ),
    OhadaIncomeStatementLineSpec(
        "TB", "Sales of manufactured products", "turnover", "Turnover", 50, ("702", "703", "704")
    ),
    OhadaIncomeStatementLineSpec("TC", "Works and services sold", "turnover", "Turnover", 60, ("705", "706")),
    OhadaIncomeStatementLineSpec("TD", "Accessory income", "turnover", "Turnover", 70, ("707",)),
    OhadaIncomeStatementLineSpec(
        "TE", "Production stocked or destocked", "value_added", "Value Added", 90, ("73",)
    ),
    OhadaIncomeStatementLineSpec("TF", "Fixed production", "value_added", "Value Added", 100, ("72",)),
    OhadaIncomeStatementLineSpec("TG", "Operating subvention", "value_added", "Value Added", 110, ("71",)),
    OhadaIncomeStatementLineSpec("TH", "Other incomes", "value_added", "Value Added", 120, ("75",)),
    OhadaIncomeStatementLineSpec(
        "TI", "Operating expenses transfer", "value_added", "Value Added", 130, ("781",)
    ),
    OhadaIncomeStatementLineSpec(
        "RC", "Purchase of raw materials and stores", "value_added", "Value Added", 140, ("602",)
    ),
    OhadaIncomeStatementLineSpec(
        "RD", "Variation of stock of raw materials and stores", "value_added", "Value Added", 150, ("6032",)
    ),
    OhadaIncomeStatementLineSpec(
        "RE", "Other purchases", "value_added", "Value Added", 160, ("604", "605", "608")
    ),
    OhadaIncomeStatementLineSpec(
        "RF", "Variation of stocks of other supplies", "value_added", "Value Added", 170, ("6033",)
    ),
    OhadaIncomeStatementLineSpec("RG", "Transport", "value_added", "Value Added", 180, ("61",)),
    OhadaIncomeStatementLineSpec("RH", "External services", "value_added", "Value Added", 190, ("62", "63")),
    OhadaIncomeStatementLineSpec("RI", "Taxes and rates", "value_added", "Value Added", 200, ("64",)),
    OhadaIncomeStatementLineSpec("RJ", "Other charges", "value_added", "Value Added", 210, ("65",)),
    OhadaIncomeStatementLineSpec(
        "RK", "Personnel expenses", "gross_operating_surplus", "Gross Operating Surplus", 230, ("66",)
    ),
    OhadaIncomeStatementLineSpec(
        "TJ",
        "Provisions and depreciations written back",
        "operating_result",
        "Operating Result",
        250,
        ("791", "798", "799"),
    ),
    OhadaIncomeStatementLineSpec(
        "RL",
        "Depreciations and provisions expenses",
        "operating_result",
        "Operating Result",
        260,
        ("68", "691"),
    ),
    OhadaIncomeStatementLineSpec(
        "TK",
        "Financial revenues and assimilated products",
        "financial_result",
        "Financial Result",
        280,
        ("77",),
    ),
    OhadaIncomeStatementLineSpec(
        "TL",
        "Financial provisions and depreciations written back",
        "financial_result",
        "Financial Result",
        290,
        ("797",),
    ),
    OhadaIncomeStatementLineSpec(
        "TM",
        "Financial expenses transferred",
        "financial_result",
        "Financial Result",
        300,
        ("787",),
    ),
    OhadaIncomeStatementLineSpec(
        "RM",
        "Financial expenses and assimilated charges",
        "financial_result",
        "Financial Result",
        310,
        ("67",),
    ),
    OhadaIncomeStatementLineSpec(
        "RN",
        "Financial depreciation and provision expenses",
        "financial_result",
        "Financial Result",
        320,
        ("697",),
    ),
    OhadaIncomeStatementLineSpec(
        "TN", "Income from disposal of fixed assets", "off_ordinary_result", "Off Ordinary Activities", 350, ("82",)
    ),
    OhadaIncomeStatementLineSpec(
        "TO", "Other incomes OOA", "off_ordinary_result", "Off Ordinary Activities", 360, ("84", "86", "88")
    ),
    OhadaIncomeStatementLineSpec(
        "RO",
        "Book value on disposal of fixed assets",
        "off_ordinary_result",
        "Off Ordinary Activities",
        370,
        ("81",),
    ),
    OhadaIncomeStatementLineSpec(
        "RP", "Other charges OOA", "off_ordinary_result", "Off Ordinary Activities", 380, ("83", "85")
    ),
    OhadaIncomeStatementLineSpec(
        "RQ", "Personnel participation", "appropriations", "Personnel Participation and Tax", 400, ("87",)
    ),
    OhadaIncomeStatementLineSpec("RS", "Income tax", "appropriations", "Personnel Participation and Tax", 410, ("89",)),
)


OHADA_FORMULA_LINE_SPECS: tuple[OhadaIncomeStatementLineSpec, ...] = (
    OhadaIncomeStatementLineSpec(
        "XA", "COMMERCIAL MARGIN", "commercial_margin", "Commercial Margin", 40, formula_components=("TA", "RA", "RB")
    ),
    OhadaIncomeStatementLineSpec(
        "XB", "TURNOVER", "turnover", "Turnover", 80, formula_components=("TA", "TB", "TC", "TD")
    ),
    OhadaIncomeStatementLineSpec(
        "XC",
        "VALUE ADDED",
        "value_added",
        "Value Added",
        220,
        formula_components=("XB", "RA", "RB", "TE", "TF", "TG", "TH", "TI", "RC", "RD", "RE", "RF", "RG", "RH", "RI", "RJ"),
    ),
    OhadaIncomeStatementLineSpec(
        "XD",
        "GROSS OPERATING SURPLUS",
        "gross_operating_surplus",
        "Gross Operating Surplus",
        240,
        formula_components=("XC", "RK"),
    ),
    OhadaIncomeStatementLineSpec(
        "XE", "OPERATING RESULT", "operating_result", "Operating Result", 270, formula_components=("XD", "TJ", "RL")
    ),
    OhadaIncomeStatementLineSpec(
        "XF",
        "FINANCIAL RESULT",
        "financial_result",
        "Financial Result",
        330,
        formula_components=("TK", "TL", "TM", "RM", "RN"),
    ),
    OhadaIncomeStatementLineSpec(
        "XG", "RESULT OF ORDINARY ACTIVITIES", "financial_result", "Financial Result", 340, formula_components=("XE", "XF")
    ),
    OhadaIncomeStatementLineSpec(
        "XH",
        "RESULT OF OFF ORDINARY ACTIVITIES",
        "off_ordinary_result",
        "Off Ordinary Activities",
        390,
        formula_components=("TN", "TO", "RO", "RP"),
    ),
    OhadaIncomeStatementLineSpec(
        "XI",
        "NET RESULT",
        "appropriations",
        "Personnel Participation and Tax",
        420,
        formula_components=("XG", "XH", "RQ", "RS"),
    ),
)


OHADA_LINE_SPECS: tuple[OhadaIncomeStatementLineSpec, ...] = tuple(
    sorted(OHADA_BASE_LINE_SPECS + OHADA_FORMULA_LINE_SPECS, key=lambda spec: spec.display_order)
)

OHADA_LINE_SPEC_BY_CODE = {spec.code: spec for spec in OHADA_LINE_SPECS}
OHADA_BASE_LINE_SPEC_BY_CODE = {spec.code: spec for spec in OHADA_BASE_LINE_SPECS}
OHADA_ALL_PREFIXES = tuple(prefix for spec in OHADA_BASE_LINE_SPECS for prefix in spec.prefixes)
