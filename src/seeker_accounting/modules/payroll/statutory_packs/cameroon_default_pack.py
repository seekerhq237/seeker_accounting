"""Cameroon 2024 statutory payroll pack — authoritative structured data definition.

This module owns the canonical pack data.  The seed service and statutory
pack service read from here; no pack-specific logic lives elsewhere.

All monetary values are in XAF (Central African CFA franc).
All rates are percentages unless stated otherwise.

Pack version: CMR_2024_V1 (R2 hardened)
Last verified: 2025-01

Verification status legend:
  VERIFIED     — cross-checked against cited legal source; correct as of last verification date
  PROVISIONAL  — commonly cited in practice, consistent with known regulations, but the exact
                 statutory instrument could not be independently parsed/confirmed
  UNVERIFIED   — placeholder or estimated; requires manual confirmation before production use

Authoritative statutory references:
  - CGI Art. 32:  30 % abattement forfaitaire for professional expenses          [VERIFIED]
  - CGI Art. 33:  500,000 XAF annual deduction (minimum vital non imposable)     [VERIFIED]
  - CGI Art. 69:  IRPP progressive bracket schedule — 10/15/25/35 %              [VERIFIED]
  - CGI Art. 165: Centimes Additionnels Communaux — 10 % of IRPP                 [VERIFIED]
  - Décret N° 2014/2377 / CNPS:
      • PVID pension 8.4 % total = employee 4.2 % + employer 4.2 %              [VERIFIED]
      • Contributory salary ceiling 750,000 XAF/month for PVID and PF            [VERIFIED]
      • Family Allowances (PF) — general regime 7 %                              [VERIFIED]
      • Family Allowances — agricultural 5.65 %, private education 3.7 %         [PROVISIONAL]
      • Accident risk groups: A = 1.75 %, B = 2.5 %, C = 5 %                    [VERIFIED A / PROVISIONAL B,C]
  - Loi de Finances:
      • CCF / CFC (Crédit Foncier) — 1 % employee salary deduction              [VERIFIED]
      • FNE salariale — 1 % employee salary deduction                            [VERIFIED]
      • FNE patronale — 2.5 % employer contribution                              [VERIFIED — barème]
  - DGI monthly withholding barème:
      • CRTV (Redevance Audiovisuelle) — bracket-based monthly schedule          [PROVISIONAL]
      • TDL (Taxe de Développement Local) — fixed monthly brackets               [PROVISIONAL]
  - Code du Travail Art. 80:
      • Overtime Day Tier 1 = 120 % (first 8 hrs/wk)                              [VERIFIED]
      • Overtime Day Tier 2 = 130 % (next 8 hrs/wk)                               [VERIFIED]
      • Overtime Day Tier 3 = 140 % (next 4 hrs/wk, max 20 hrs/wk)               [VERIFIED]
      • Overtime Night = 150 %                                                     [VERIFIED]
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


# ── Verification status enum ──────────────────────────────────────────────────

class VerificationStatus(str, Enum):
    """Classification of how well a pack item has been verified against official sources."""
    VERIFIED = "verified"
    PROVISIONAL = "provisional"
    UNVERIFIED = "unverified"


# ── Item-level verification metadata ──────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class VerificationRecord:
    """Verification metadata attached to each component or rule set seed."""
    status: VerificationStatus
    source: str
    notes: str = ""


# ── Pack identity ─────────────────────────────────────────────────────────────

PACK_CODE = "CMR_2024_V1"
PACK_DISPLAY_NAME = "Cameroon 2024 Statutory Pack (R2)"
PACK_COUNTRY_CODE = "CM"
PACK_EFFECTIVE_FROM = date(2024, 1, 1)
PACK_DESCRIPTION = (
    "Cameroon payroll pack covering IRPP withholding barème (with 30 % abattement and "
    "500,000 XAF minimum vital), CNPS pension (4.2 % employee / 4.2 % employer), "
    "family allowances (7 % general regime), accident risk A/B/C, TDL, CCF, FNE, "
    "CRTV, and standard payroll components. "
    "R2-hardened with per-item verification metadata. "
    "Review PROVISIONAL / UNVERIFIED items against current Finance Law before production use."
)
PACK_VERSION_NOTES = "R2 compliance hardening — per-item verification, naming cleanup, metadata."
PACK_LAST_VERIFIED = "2025-01"

# ── Component seed definitions ────────────────────────────────────────────────
# Each entry: (code, display_name, type_code, calculation_method_code, is_taxable, is_pensionable, verification)

COMPONENT_SEEDS: list[tuple[str, str, str, str, bool, bool, VerificationRecord]] = [
    # ── Earnings ─────────────────────────────────────────────────────────────
    ("BASE_SALARY", "Base Salary", "earning", "fixed_amount", True, True,
     VerificationRecord(VerificationStatus.VERIFIED, "Labour Code / standard practice",
                        "Base salary is the contractual fixed pay; subject to IRPP and pensionable.")),
    ("OVERTIME", "Overtime", "earning", "percentage", True, True,
     VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                        "Generic overtime component; use tier-specific components for Cameroon compliance.")),
    ("OVERTIME_DAY_T1", "Overtime Day Tier 1 (120%)", "earning", "hourly", True, True,
     VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                        "First 8 hours/week of daytime overtime at 120% of hourly rate.")),
    ("OVERTIME_DAY_T2", "Overtime Day Tier 2 (130%)", "earning", "hourly", True, True,
     VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                        "Next 8 hours/week of daytime overtime at 130% of hourly rate.")),
    ("OVERTIME_DAY_T3", "Overtime Day Tier 3 (140%)", "earning", "hourly", True, True,
     VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                        "Next 4 hours/week of daytime overtime at 140% of hourly rate (max 20 hrs/week).")),
    ("OVERTIME_NIGHT", "Overtime Night (150%)", "earning", "hourly", True, True,
     VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                        "Night overtime hours at 150% of hourly rate.")),
    ("HOUSING_ALLOWANCE", "Housing Allowance", "earning", "fixed_amount", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Standard Cameroon payroll practice",
                        "Non-taxable housing allowance; confirmed non-pensionable.")),
    ("TRANSPORT_ALLOWANCE", "Transport Allowance", "earning", "fixed_amount", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Standard Cameroon payroll practice",
                        "Non-taxable transport allowance; confirmed non-pensionable.")),
    # ── Employee deductions ───────────────────────────────────────────────────
    ("EMPLOYEE_CNPS", "CNPS Pension (Employee)", "deduction", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Décret N° 2014/2377 — CNPS",
                        "4.2 % of pensionable gross capped at 750,000 XAF/month.")),
    ("IRPP", "IRPP Withholding", "tax", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "CGI Art. 69",
                        "Progressive 10/15/25/35 % on annual taxable income.")),
    ("CAC", "Centimes Additionnels Communaux (CAC)", "tax", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "CGI Art. 165",
                        "10 % of computed IRPP amount.")),
    ("TDL", "Taxe de Développement Local (TDL)", "tax", "rule_based", False, False,
     VerificationRecord(VerificationStatus.PROVISIONAL, "DGI monthly withholding barème",
                        "Fixed-amount brackets tied to gross salary; bracket boundaries are from DGI publications but exact values need annual confirmation.")),
    ("CRTV", "Redevance Audiovisuelle (CRTV)", "deduction", "rule_based", False, False,
     VerificationRecord(VerificationStatus.PROVISIONAL, "DGI monthly withholding barème",
                        "Bracket-based monthly fixed amounts; commonly published schedule but exact amounts require annual DGI circular confirmation.")),
    ("CFC_HLF", "Crédit Foncier du Cameroun (CFC)", "deduction", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Loi de Finances — CFC / CCF",
                        "1 % of gross salary; employee-side salary deduction. Code 'CFC_HLF' retained for backward compatibility.")),
    ("FNE_EMPLOYEE", "FNE Salariale (Employee)", "deduction", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Loi de Finances — FNE",
                        "1 % of gross salary; employee-side salary deduction.")),
    # ── Employer contributions ────────────────────────────────────────────────
    ("EMPLOYER_CNPS", "CNPS Pension (Employer)", "employer_contribution", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Décret N° 2014/2377 — CNPS",
                        "4.2 % of pensionable gross capped at 750,000 XAF/month.")),
    ("FNE", "FNE Patronale (Employer)", "employer_contribution", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Loi de Finances — FNE",
                        "2.5 % of gross salary; employer contribution.")),
    ("ACCIDENT_RISK_EMPLOYER", "Accident Risk (CNPS AT/MP)", "employer_contribution", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Décret N° 2014/2377 — CNPS AT/MP",
                        "Group A = 1.75 %; applied per company accident risk class.")),
    ("EMPLOYER_AF", "Allocations Familiales (CNPS PF)", "employer_contribution", "rule_based", False, False,
     VerificationRecord(VerificationStatus.VERIFIED, "Décret N° 2014/2377 — CNPS PF",
                        "General regime 7 %, capped at 750,000 XAF/month. Regime-specific rate selected per company settings.")),
]

# ── Bracket type alias ────────────────────────────────────────────────────────
# (line_no, lower, upper, rate_pct, fixed_amt, deduction_amt, cap_amt)
_Bracket = tuple[
    int,
    Decimal | None,
    Decimal | None,
    Decimal | None,
    Decimal | None,
    Decimal | None,
    Decimal | None,
]


def _D(v: str) -> Decimal:
    return Decimal(v)


# ── Rule set seed definitions ─────────────────────────────────────────────────
# Each entry: (code, display_name, rule_type_code, calculation_basis_code, brackets, verification)

RULE_SET_SEEDS: list[tuple[str, str, str, str, list[_Bracket], VerificationRecord]] = [
    # ── DGI IRPP main barème ──────────────────────────────────────────────────
    # Annual taxable-gross brackets; calculation engine annualises/de-annualises.
    # Rates unchanged since 2012 DGI reform (CGI Art. 69).
    (
        "DGI_IRPP_MAIN",
        "DGI IRPP Main Barème",
        "pit",
        "taxable_gross",
        [
            (1, _D("0"),       _D("2000000"),  _D("10.00"), None, None, None),
            (2, _D("2000000"), _D("3000000"),  _D("15.00"), None, None, None),
            (3, _D("3000000"), _D("5000000"),  _D("25.00"), None, None, None),
            (4, _D("5000000"), None,           _D("35.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "CGI Art. 69",
                           "Four-bracket schedule: 10/15/25/35 %. Unchanged since 2012 reform."),
    ),
    # ── DGI IRPP abattement (professional expenses + minimum vital) ──────────
    # CGI Art. 32: 30 % forfaitaire professional expenses abattement
    # CGI Art. 33: 500,000 XAF annual minimum vital non imposable deduction
    # Bracket rate = abattement percentage, deduction_amount = annual deduction.
    (
        "DGI_IRPP_ABATTEMENT",
        "DGI Professional Expenses Abattement + Minimum Vital",
        "abattement",
        "taxable_gross",
        [
            (1, None, None, _D("30.00"), None, _D("500000"), None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "CGI Art. 32 + Art. 33",
                           "30 % abattement + 500,000 XAF annual minimum vital deduction."),
    ),
    # ── TDL main brackets ─────────────────────────────────────────────────────
    # Monthly fixed-amount levy keyed to gross salary.
    # TDL was introduced by Loi de Finances 2015, modified subsequently.
    # Exact bracket boundaries and amounts from DGI withholding barème.
    (
        "TDL_MAIN",
        "Taxe de Développement Local (TDL)",
        "levy",
        "gross_salary",
        [
            (1, _D("0"),      _D("50000"),   None, _D("0"),   None, None),
            (2, _D("50000"),  _D("208333"),  None, _D("167"), None, None),
            (3, _D("208333"), None,          None, _D("250"), None, None),
        ],
        VerificationRecord(VerificationStatus.PROVISIONAL, "DGI monthly withholding barème",
                           "Fixed monthly amounts derived from annual TDL (0 / 2,000 / 3,000 XAF ÷ 12). "
                           "Bracket boundaries consistent with DGI publications; confirm annually."),
    ),
    # ── CNPS employee pension (PVID) ──────────────────────────────────────────
    # 4.2 % of pensionable gross, monthly ceiling 750,000 XAF → max 31,500 XAF.
    # Total PVID = 8.4 % split equally between employee and employer.
    (
        "CNPS_EMPLOYEE_MAIN",
        "CNPS Employee Pension (PVID)",
        "pension_employee",
        "gross_salary",
        [
            (1, _D("0"), _D("750000"), _D("4.20"), None, None, _D("31500")),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Décret N° 2014/2377 — CNPS",
                           "Employee PVID = 4.2 %. Ceiling 750,000 XAF → max contribution 31,500 XAF."),
    ),
    # ── CNPS employer pension (PVID) ──────────────────────────────────────────
    # 4.2 % of pensionable gross, same monthly ceiling → max 31,500 XAF.
    (
        "CNPS_EMPLOYER_MAIN",
        "CNPS Employer Pension (PVID)",
        "pension_employer",
        "gross_salary",
        [
            (1, _D("0"), _D("750000"), _D("4.20"), None, None, _D("31500")),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Décret N° 2014/2377 — CNPS",
                           "Employer PVID = 4.2 %. Ceiling 750,000 XAF → max contribution 31,500 XAF."),
    ),
    # ── CNPS accident risk — Group A (standard) ──────────────────────────────
    # Three groups: A = 1.75 %, B = 2.5 %, C = 5 %.
    # No salary ceiling for AT/MP (accident risk is uncapped).
    (
        "ACCIDENT_RISK_STANDARD",
        "CNPS Accident Risk — Group A (Standard)",
        "accident_risk",
        "gross_salary",
        [
            (1, _D("0"), None, _D("1.75"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Décret N° 2014/2377 — CNPS AT/MP",
                           "Group A = 1.75 %. No salary cap for accident risk."),
    ),
    # ── CNPS accident risk — Group B ──────────────────────────────────────────
    (
        "ACCIDENT_RISK_B",
        "CNPS Accident Risk — Group B",
        "accident_risk",
        "gross_salary",
        [
            (1, _D("0"), None, _D("2.50"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.PROVISIONAL, "CNPS AT/MP classification",
                           "Group B = 2.5 %. Commonly cited; confirm sector classification."),
    ),
    # ── CNPS accident risk — Group C ──────────────────────────────────────────
    (
        "ACCIDENT_RISK_C",
        "CNPS Accident Risk — Group C",
        "accident_risk",
        "gross_salary",
        [
            (1, _D("0"), None, _D("5.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.PROVISIONAL, "CNPS AT/MP classification",
                           "Group C = 5.0 %. Commonly cited; confirm sector classification."),
    ),
    # ── CNPS Family Allowances (PF) — General Regime ─────────────────────────
    # 7 % of pensionable gross capped at 750,000 XAF/month → max 52,500 XAF.
    (
        "AF_MAIN",
        "CNPS Allocations Familiales — General Regime",
        "family_benefit",
        "gross_salary",
        [
            (1, _D("0"), _D("750000"), _D("7.00"), None, None, _D("52500")),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Décret N° 2014/2377 — CNPS PF",
                           "General regime = 7 %. Ceiling 750,000 XAF → max 52,500 XAF."),
    ),
    # ── CNPS Family Allowances — Agricultural Regime ─────────────────────────
    (
        "AF_AGRICULTURAL",
        "CNPS Allocations Familiales — Agricultural Regime",
        "family_benefit",
        "gross_salary",
        [
            (1, _D("0"), _D("750000"), _D("5.65"), None, None, _D("42375")),
        ],
        VerificationRecord(VerificationStatus.PROVISIONAL, "CNPS PF regime classification",
                           "Agricultural regime = 5.65 %. Commonly cited; confirm with CNPS decree."),
    ),
    # ── CNPS Family Allowances — Private Education Regime ────────────────────
    (
        "AF_EDUCATION",
        "CNPS Allocations Familiales — Private Education Regime",
        "family_benefit",
        "gross_salary",
        [
            (1, _D("0"), _D("750000"), _D("3.70"), None, None, _D("27750")),
        ],
        VerificationRecord(VerificationStatus.PROVISIONAL, "CNPS PF regime classification",
                           "Private education regime = 3.7 %. Commonly cited; confirm with CNPS decree."),
    ),
    # ── CCF / CFC (Crédit Foncier du Cameroun) ───────────────────────────────
    # 1 % of gross salary — employee-side only (salary deduction).
    (
        "CCF_MAIN",
        "CFC / Crédit Foncier du Cameroun (Employee)",
        "levy",
        "gross_salary",
        [
            (1, _D("0"), None, _D("1.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Loi de Finances — CFC / CCF",
                           "1 % of gross salary. No employer-side CFC confirmed."),
    ),
    # ── FNE Employee (Salariale) ──────────────────────────────────────────────
    # 1 % of gross salary, employee side.
    (
        "FNE_EMPLOYEE_MAIN",
        "FNE Salariale (Employee)",
        "levy",
        "gross_salary",
        [
            (1, _D("0"), None, _D("1.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Loi de Finances — FNE",
                           "1 % of gross salary; employee-side salary deduction."),
    ),
    # ── FNE Employer (Patronale) ──────────────────────────────────────────────
    # 2.5 % of gross salary, employer side (barème-verified).
    (
        "FNE_EMPLOYER_MAIN",
        "FNE Patronale (Employer)",
        "levy",
        "gross_salary",
        [
            (1, _D("0"), None, _D("2.50"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Loi de Finances — FNE / DGI barème cross-check",
                           "2.5 % of gross salary; employer-side contribution. Verified against DGI IRPP barème DSSI."),
    ),
    # ── CRTV (Redevance Audiovisuelle) ────────────────────────────────────────
    # Bracket-based monthly fixed amount keyed on gross salary.
    # Schedule verified against DGI IRPP barème DSSI (9 brackets).
    (
        "CRTV_MAIN",
        "Redevance Audiovisuelle (CRTV)",
        "levy",
        "gross_salary",
        [
            (1, _D("0"),       _D("50000"),    None, _D("0"),     None, None),
            (2, _D("50000"),   _D("100000"),   None, _D("750"),   None, None),
            (3, _D("100000"),  _D("200000"),   None, _D("1950"),  None, None),
            (4, _D("200000"),  _D("300000"),   None, _D("3250"),  None, None),
            (5, _D("300000"),  _D("500000"),   None, _D("4550"),  None, None),
            (6, _D("500000"),  _D("700000"),   None, _D("5850"),  None, None),
            (7, _D("700000"),  _D("800000"),   None, _D("9750"),  None, None),
            (8, _D("800000"),  _D("1000000"),  None, _D("12350"), None, None),
            (9, _D("1000000"), None,           None, _D("13000"), None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "DGI IRPP barème DSSI",
                           "9-bracket schedule verified against DGI barème indicatif de liquidation de l'IRPP."),
    ),
    # ── Overtime standard (generic fallback) ─────────────────────────────────
    # 150 % overtime = 50 % premium above base hourly rate.
    # Retained for backward compatibility; prefer tier-specific rule sets.
    (
        "OVERTIME_STANDARD",
        "Overtime Standard Rate (150 %)",
        "overtime",
        "basic_salary",
        [
            (1, None, None, _D("50.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                           "Generic 150 % (50 % premium). Use tier-specific rule sets for Cameroon compliance."),
    ),
    # ── Overtime Day Tier 1 (120 %) ───────────────────────────────────────────
    # First 8 hours/week of daytime overtime — 20 % premium.
    (
        "OVERTIME_DAY_T1",
        "Overtime Day Tier 1 (120 %)",
        "overtime",
        "basic_salary",
        [
            (1, None, None, _D("20.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                           "First 8 hrs/week daytime OT at 120 % (20 % premium)."),
    ),
    # ── Overtime Day Tier 2 (130 %) ───────────────────────────────────────────
    # Next 8 hours/week of daytime overtime — 30 % premium.
    (
        "OVERTIME_DAY_T2",
        "Overtime Day Tier 2 (130 %)",
        "overtime",
        "basic_salary",
        [
            (1, None, None, _D("30.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                           "Next 8 hrs/week daytime OT at 130 % (30 % premium)."),
    ),
    # ── Overtime Day Tier 3 (140 %) ───────────────────────────────────────────
    # Next 4 hours/week of daytime overtime — 40 % premium (max 20 hrs/week total).
    (
        "OVERTIME_DAY_T3",
        "Overtime Day Tier 3 (140 %)",
        "overtime",
        "basic_salary",
        [
            (1, None, None, _D("40.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                           "Next 4 hrs/week daytime OT at 140 % (40 % premium). Max 20 hrs/week total."),
    ),
    # ── Overtime Night (150 %) ────────────────────────────────────────────────
    # Night overtime — 50 % premium.
    (
        "OVERTIME_NIGHT",
        "Overtime Night (150 %)",
        "overtime",
        "basic_salary",
        [
            (1, None, None, _D("50.00"), None, None, None),
        ],
        VerificationRecord(VerificationStatus.VERIFIED, "Code du Travail Art. 80",
                           "Night overtime at 150 % (50 % premium)."),
    ),
]


# ── Pack-level verification summary ──────────────────────────────────────────

def get_pack_verification_summary() -> dict[str, int]:
    """Return counts of verified / provisional / unverified items across components and rule sets."""
    counts: dict[str, int] = {"verified": 0, "provisional": 0, "unverified": 0}
    for *_fields, vr in COMPONENT_SEEDS:
        counts[vr.status.value] += 1
    for *_fields, vr in RULE_SET_SEEDS:
        counts[vr.status.value] += 1
    return counts


def get_verification_matrix() -> list[dict[str, str]]:
    """Return a flat list of all pack items with their verification details."""
    rows: list[dict[str, str]] = []
    for code, display_name, *_rest, vr in COMPONENT_SEEDS:
        rows.append({
            "item_type": "component",
            "code": code,
            "display_name": display_name,
            "status": vr.status.value,
            "source": vr.source,
            "notes": vr.notes,
        })
    for code, display_name, *_rest, vr in RULE_SET_SEEDS:
        rows.append({
            "item_type": "rule_set",
            "code": code,
            "display_name": display_name,
            "status": vr.status.value,
            "source": vr.source,
            "notes": vr.notes,
        })
    return rows
