"""Validation script for OHADA standards-conformance spec corrections.

Verifies:
  A) XI (Net Result) formula line exists with correct components
  B) Equity lines CH-CM have correct prefix assignments
  C) Account 408 is included in DK (not excluded)
  D) Prefix 41 is in DM, not DL
  + Structural integrity checks (no duplicate prefixes, totals match)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from seeker_accounting.modules.reporting.specs.ohada_income_statement_spec import (
    OHADA_LINE_SPECS,
    OHADA_FORMULA_LINE_SPECS,
    OHADA_BASE_LINE_SPECS,
    OHADA_LINE_SPEC_BY_CODE,
)
from seeker_accounting.modules.reporting.specs.ohada_balance_sheet_spec import (
    OHADA_BALANCE_SHEET_LINE_SPECS,
    OHADA_BALANCE_SHEET_SPEC_BY_CODE,
    OHADA_BALANCE_SHEET_BASE_LINE_SPECS,
    OHADA_BALANCE_SHEET_TOTAL_LINE_SPECS,
)

passed = 0
failed = 0


def check(description: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {description}")
    else:
        failed += 1
        msg = f"  FAIL: {description}"
        if detail:
            msg += f" -- {detail}"
        print(msg)


# ── A: XI formula line ──────────────────────────────────────────────
print("\n=== A: XI Net Result formula line ===")

xi = OHADA_LINE_SPEC_BY_CODE.get("XI")
check("XI line exists in OHADA_LINE_SPECS", xi is not None)
if xi:
    check("XI is a formula line", xi.is_formula)
    check(
        "XI formula_components are (XG, XH, RQ, RS)",
        xi.formula_components == ("XG", "XH", "RQ", "RS"),
        f"got {xi.formula_components}",
    )
    check("XI label is 'NET RESULT'", xi.label == "NET RESULT", f"got '{xi.label}'")
    check("XI section is 'appropriations'", xi.section_code == "appropriations", f"got '{xi.section_code}'")
    check("XI display_order > XH display_order", xi.display_order > OHADA_LINE_SPEC_BY_CODE["XH"].display_order)
    check("XI display_order > RS display_order", xi.display_order > OHADA_LINE_SPEC_BY_CODE["RS"].display_order)
    check("XI is in OHADA_FORMULA_LINE_SPECS", any(s.code == "XI" for s in OHADA_FORMULA_LINE_SPECS))

# All XI components must exist
for comp in ("XG", "XH", "RQ", "RS"):
    check(f"XI component '{comp}' exists in line specs", comp in OHADA_LINE_SPEC_BY_CODE)

# ── B: Equity line prefix corrections ────────────────────────────────
print("\n=== B: Equity lines CH-CM prefix assignments ===")

def get_bs_prefixes(code: str) -> list[str]:
    spec = OHADA_BALANCE_SHEET_SPEC_BY_CODE.get(code)
    if not spec or not spec.selectors:
        return []
    return [p for sel in spec.selectors for p in sel.include_prefixes]

check("CG includes '118'", "118" in get_bs_prefixes("CG"), f"CG prefixes: {get_bs_prefixes('CG')}")
check("CG includes '111'", "111" in get_bs_prefixes("CG"))
check("CG includes '112'", "112" in get_bs_prefixes("CG"))
check("CG includes '113'", "113" in get_bs_prefixes("CG"))

check("CH prefix is ('12',)", get_bs_prefixes("CH") == ["12"], f"CH prefixes: {get_bs_prefixes('CH')}")
check("CI prefix is ('13',)", get_bs_prefixes("CI") == ["13"], f"CI prefixes: {get_bs_prefixes('CI')}")
check("CL prefix is ('14',)", get_bs_prefixes("CL") == ["14"], f"CL prefixes: {get_bs_prefixes('CL')}")
check("CM prefix is ('15',)", get_bs_prefixes("CM") == ["15"], f"CM prefixes: {get_bs_prefixes('CM')}")

# Verify no prefix appears in multiple equity lines
equity_codes = ("CB", "CD", "CE", "CF", "CG", "CH", "CI", "CL", "CM")
all_equity_prefixes = []
for ec in equity_codes:
    for p in get_bs_prefixes(ec):
        all_equity_prefixes.append((p, ec))

seen = {}
dup_issues = []
for prefix, code in all_equity_prefixes:
    if prefix in seen:
        dup_issues.append(f"'{prefix}' in both {seen[prefix]} and {code}")
    seen[prefix] = code
check("No duplicate prefixes across equity lines", len(dup_issues) == 0, "; ".join(dup_issues))

# ── C: Account 408 included in DK ──────────────────────────────────
print("\n=== C: Account 408 inclusion in DK ===")

dk = OHADA_BALANCE_SHEET_SPEC_BY_CODE["DK"]
dk_sel = dk.selectors[0]
check("DK includes prefix '40'", "40" in dk_sel.include_prefixes)
check("DK does NOT exclude '408'", "408" not in dk_sel.exclude_prefixes and "408" not in dk_sel.exclude_exact_codes,
      f"exclude_prefixes={dk_sel.exclude_prefixes}, exclude_exact={dk_sel.exclude_exact_codes}")

# ── D: Prefix 41 moved from DL to DM ───────────────────────────────
print("\n=== D: Prefix 41 moved from DL to DM ===")

dl = OHADA_BALANCE_SHEET_SPEC_BY_CODE["DL"]
dm = OHADA_BALANCE_SHEET_SPEC_BY_CODE["DM"]
dl_prefixes = [p for sel in dl.selectors for p in sel.include_prefixes]
dm_prefixes = [p for sel in dm.selectors for p in sel.include_prefixes]

check("DL does NOT include prefix '41'", "41" not in dl_prefixes, f"DL prefixes: {dl_prefixes}")
check("DL still includes '42', '43', '44'", all(p in dl_prefixes for p in ("42", "43", "44")), f"DL prefixes: {dl_prefixes}")
check("DM includes prefix '41'", "41" in dm_prefixes, f"DM prefixes: {dm_prefixes}")
check("DM still includes '185', '45', '46', '47'", all(p in dm_prefixes for p in ("185", "45", "46", "47")), f"DM prefixes: {dm_prefixes}")

# 419 must be excluded from DM (customer advances belong in DJ)
dm_excludes = [p for sel in dm.selectors for p in sel.exclude_prefixes]
dm_excludes_exact = [p for sel in dm.selectors for p in sel.exclude_exact_codes]
check("DM excludes '419'", "419" in dm_excludes or "419" in dm_excludes_exact,
      f"DM exclude_prefixes={dm_excludes}, exclude_exact={dm_excludes_exact}")

# ── Structural integrity ─────────────────────────────────────────────
print("\n=== Structural integrity ===")

# IS: all formula components reference existing line codes
for spec in OHADA_FORMULA_LINE_SPECS:
    for comp in spec.formula_components:
        check(f"IS formula {spec.code} component '{comp}' exists", comp in OHADA_LINE_SPEC_BY_CODE)

# IS: display_order is monotonically increasing
is_orders = [s.display_order for s in OHADA_LINE_SPECS]
check("IS display_order is sorted", is_orders == sorted(is_orders), f"orders: {is_orders}")

# BS: all total_components reference existing line codes
for spec in OHADA_BALANCE_SHEET_TOTAL_LINE_SPECS:
    for comp in spec.total_components:
        check(f"BS total {spec.code} component '{comp}' exists",
              comp in OHADA_BALANCE_SHEET_SPEC_BY_CODE,
              f"missing '{comp}'")

# CP total still has all equity components
cp = OHADA_BALANCE_SHEET_SPEC_BY_CODE["CP"]
check("CP total_components = (CB,CD,CE,CF,CG,CH,CI,CL,CM)",
      cp.total_components == ("CB", "CD", "CE", "CF", "CG", "CH", "CI", "CL", "CM"),
      f"got {cp.total_components}")

# DZ total still balances
dz = OHADA_BALANCE_SHEET_SPEC_BY_CODE["DZ"]
check("DZ total_components = (CP,DF,DP,DT,DU)",
      dz.total_components == ("CP", "DF", "DP", "DT", "DU"),
      f"got {dz.total_components}")

# BZ total
bz = OHADA_BALANCE_SHEET_SPEC_BY_CODE["BZ"]
check("BZ total_components = (AZ,BK,BT,BU)",
      bz.total_components == ("AZ", "BK", "BT", "BU"),
      f"got {bz.total_components}")

# ── Summary ─────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"RESULTS: {passed} passed, {failed} failed")
if failed > 0:
    print("VALIDATION FAILED")
    sys.exit(1)
else:
    print("ALL CORRECTIONS VERIFIED")
    sys.exit(0)
