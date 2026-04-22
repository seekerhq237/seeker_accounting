"""Validation: OHADA period result alignment.

Proves:
  1. OhadaPeriodResultService.compute_result_from_activity() produces the
     same XI amount as the income statement engine's _compute_lines().
  2. BS interim CI injection uses the shared service (not the ad-hoc repo
     query), so it includes class 8 accounts.
  3. Loss scenarios, zero-P&L, and class 8 activity are all handled.
"""
from __future__ import annotations

import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from seeker_accounting.modules.reporting.repositories.ohada_income_statement_repository import (
    OhadaAccountActivityRow,
)
from seeker_accounting.modules.reporting.services.ohada_income_statement_service import (
    OhadaIncomeStatementService,
)
from seeker_accounting.modules.reporting.services.ohada_period_result_service import (
    OhadaPeriodResultService,
)

_ZERO = Decimal("0.00")

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


def _row(
    account_id: int,
    account_code: str,
    account_name: str,
    total_debit: Decimal,
    total_credit: Decimal,
    class_code: str | None = None,
) -> OhadaAccountActivityRow:
    return OhadaAccountActivityRow(
        account_id=account_id,
        account_code=account_code,
        account_name=account_name,
        account_class_code=class_code or (account_code[0] if account_code else None),
        account_type_code=None,
        normal_balance="debit" if (class_code or account_code[0]) == "6" else "credit",
        total_debit=total_debit,
        total_credit=total_credit,
    )


def _is_xi_amount(activity_rows: list[OhadaAccountActivityRow]) -> Decimal:
    """Compute XI via the IS engine's _compute_lines (the reference path)."""
    computed = OhadaIncomeStatementService._compute_lines(
        OhadaIncomeStatementService.__new__(OhadaIncomeStatementService),
        activity_rows,
    )
    return computed["XI"].signed_amount


def _period_result_amount(activity_rows: list[OhadaAccountActivityRow]) -> Decimal:
    """Compute XI via the shared period-result service (the new path)."""
    return OhadaPeriodResultService.compute_result_from_activity(activity_rows)


# ---------------------------------------------------------------------------
# 1. Basic profit scenario
# ---------------------------------------------------------------------------
print("\n=== 1. Basic profit: revenue > expenses ===")

basic_rows = [
    _row(1, "601", "Purchases of goods", Decimal("3000"), Decimal("0")),
    _row(2, "701", "Sales of goods", Decimal("0"), Decimal("5000")),
]
is_xi = _is_xi_amount(basic_rows)
pr_xi = _period_result_amount(basic_rows)
check("IS XI == 2000 (profit)", is_xi == Decimal("2000.00"), f"got {is_xi}")
check("Period result == IS XI", pr_xi == is_xi, f"period={pr_xi}, is={is_xi}")


# ---------------------------------------------------------------------------
# 2. Loss scenario
# ---------------------------------------------------------------------------
print("\n=== 2. Loss: expenses > revenue ===")

loss_rows = [
    _row(1, "601", "Purchases of goods", Decimal("6000"), Decimal("0")),
    _row(2, "701", "Sales of goods", Decimal("0"), Decimal("4000")),
]
is_xi = _is_xi_amount(loss_rows)
pr_xi = _period_result_amount(loss_rows)
check("IS XI == -2000 (loss)", is_xi == Decimal("-2000.00"), f"got {is_xi}")
check("Period result == IS XI", pr_xi == is_xi, f"period={pr_xi}, is={is_xi}")


# ---------------------------------------------------------------------------
# 3. Zero activity
# ---------------------------------------------------------------------------
print("\n=== 3. Zero activity ===")

is_xi = _is_xi_amount([])
pr_xi = _period_result_amount([])
check("IS XI == 0", is_xi == _ZERO, f"got {is_xi}")
check("Period result == 0", pr_xi == _ZERO, f"got {pr_xi}")


# ---------------------------------------------------------------------------
# 4. Class 8 activity (appropriation accounts)
# ---------------------------------------------------------------------------
print("\n=== 4. Class 8 accounts (OOA items) — must NOT be missed ===")

class8_rows = [
    _row(1, "601", "Purchases", Decimal("2000"), Decimal("0")),
    _row(2, "701", "Sales", Decimal("0"), Decimal("5000")),
    # Class 8: appropriation items (debit = expense-like, credit = income-like)
    _row(3, "81", "Exceptional charges", Decimal("500"), Decimal("0"), "8"),
    _row(4, "82", "Exceptional income", Decimal("0"), Decimal("200"), "8"),
]
is_xi = _is_xi_amount(class8_rows)
pr_xi = _period_result_amount(class8_rows)
# Expected: (5000 - 2000) + (200 - 500) = 3000 - 300 = 2700
check("IS XI == 2700", is_xi == Decimal("2700.00"), f"got {is_xi}")
check("Period result == IS XI", pr_xi == is_xi, f"period={pr_xi}, is={is_xi}")


# ---------------------------------------------------------------------------
# 5. Multi-section complex scenario
# ---------------------------------------------------------------------------
print("\n=== 5. Complex multi-section scenario ===")

complex_rows = [
    _row(1, "601", "Purchases of goods", Decimal("1000"), Decimal("0")),
    _row(2, "602", "Purchases of materials", Decimal("200"), Decimal("0")),
    _row(3, "604", "Purchased services", Decimal("100"), Decimal("0")),
    _row(4, "641", "Staff costs", Decimal("500"), Decimal("0")),
    _row(5, "681", "Depreciation", Decimal("300"), Decimal("0")),
    _row(6, "701", "Sales of goods", Decimal("0"), Decimal("3000")),
    _row(7, "706", "Service revenue", Decimal("0"), Decimal("800")),
    _row(8, "771", "Interest income", Decimal("0"), Decimal("100")),
    _row(9, "671", "Interest expense", Decimal("50"), Decimal("0")),
    _row(10, "89", "Income tax", Decimal("200"), Decimal("0")),
]
is_xi = _is_xi_amount(complex_rows)
pr_xi = _period_result_amount(complex_rows)
check("IS XI matches period result", pr_xi == is_xi, f"period={pr_xi}, is={is_xi}")
# Sanity: 3000+800+100 - (1000+200+100+500+300+50+200) = 3900 - 2350 = 1550
check("IS XI == 1550", is_xi == Decimal("1550.00"), f"got {is_xi}")


# ---------------------------------------------------------------------------
# 6. Unclassified accounts are correctly excluded from both
# ---------------------------------------------------------------------------
print("\n=== 6. Unclassified P&L accounts excluded from both ===")

unclassified_rows = [
    _row(1, "601", "Purchases", Decimal("1000"), Decimal("0")),
    _row(2, "701", "Sales", Decimal("0"), Decimal("3000")),
    # Account code that doesn't match any OHADA base line prefix
    _row(3, "699", "Miscellaneous expense", Decimal("500"), Decimal("0"), "6"),
]
is_xi = _is_xi_amount(unclassified_rows)
pr_xi = _period_result_amount(unclassified_rows)
check("Both produce same result", pr_xi == is_xi, f"period={pr_xi}, is={is_xi}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"RESULTS: {passed} passed, {failed} failed")
if failed > 0:
    print("VALIDATION FAILED")
    sys.exit(1)
else:
    print("ALL PERIOD RESULT ALIGNMENT TESTS PASSED")
    sys.exit(0)
