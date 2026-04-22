"""Validation script for interim balance-sheet self-balancing.

Proves:
  1. OHADA interim BS balances when YTD profit exists but no closing entry posted.
  2. IAS interim BS balances under the same condition.
  3. Post-closing scenarios do not double count.
  4. Loss scenarios also work correctly.
"""
from __future__ import annotations

import sys
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from seeker_accounting.modules.reporting.dto.reporting_filter_dto import ReportingFilterDTO
from seeker_accounting.modules.reporting.repositories.ohada_balance_sheet_repository import (
    OhadaBalanceSheetAccountRow,
    OhadaBalanceSheetRepository,
)
from seeker_accounting.modules.reporting.repositories.ias_balance_sheet_repository import (
    IasBalanceSheetAccountRow,
    IasBalanceSheetRepository,
)
from seeker_accounting.modules.reporting.services.ohada_balance_sheet_service import (
    OhadaBalanceSheetService,
)
from seeker_accounting.modules.reporting.services.ohada_period_result_service import (
    OhadaPeriodResultService,
)
from seeker_accounting.modules.reporting.services.ias_balance_sheet_service import (
    IasBalanceSheetService,
)
from seeker_accounting.modules.reporting.services.balance_sheet_template_service import (
    BalanceSheetTemplateService,
)

_ZERO = Decimal("0.00")
_COMPANY_ID = 1
_DATE = date(2025, 6, 30)

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


# ---------------------------------------------------------------------------
# Helper: fake UoW + repo factories
# ---------------------------------------------------------------------------

@contextmanager
def _fake_uow():
    uow = MagicMock()
    uow.session = MagicMock()
    yield uow


def _make_ohada_bs_account(
    account_id: int,
    account_code: str,
    account_name: str,
    total_debit: Decimal,
    total_credit: Decimal,
    normal_balance: str = "credit",
) -> OhadaBalanceSheetAccountRow:
    class_code = account_code[0] if account_code else None
    return OhadaBalanceSheetAccountRow(
        account_id=account_id,
        account_code=account_code,
        account_name=account_name,
        account_class_code=class_code,
        account_type_code=None,
        account_type_section_code=None,
        normal_balance=normal_balance,
        is_active=True,
        allow_manual_posting=True,
        is_control_account=False,
        total_debit=total_debit,
        total_credit=total_credit,
    )


def _make_ias_bs_account(
    account_id: int,
    account_code: str,
    account_name: str,
    total_debit: Decimal,
    total_credit: Decimal,
    normal_balance: str = "credit",
    section_code: str | None = None,
) -> IasBalanceSheetAccountRow:
    class_code = account_code[0] if account_code else None
    return IasBalanceSheetAccountRow(
        account_id=account_id,
        account_code=account_code,
        account_name=account_name,
        account_class_code=class_code,
        account_class_name=None,
        account_type_code=None,
        account_type_name=None,
        account_type_section_code=section_code,
        normal_balance=normal_balance,
        is_active=True,
        allow_manual_posting=True,
        is_control_account=False,
        total_debit=total_debit,
        total_credit=total_credit,
    )


def _build_ohada_service(
    bs_rows: list[OhadaBalanceSheetAccountRow],
    ytd_profit_loss: Decimal,
) -> OhadaBalanceSheetService:
    repo = MagicMock(spec=OhadaBalanceSheetRepository)
    repo.list_balance_snapshot.return_value = bs_rows

    period_result_svc = MagicMock(spec=OhadaPeriodResultService)
    period_result_svc.compute_period_result.return_value = ytd_profit_loss

    template_svc = MagicMock(spec=BalanceSheetTemplateService)
    template_svc.get_template.return_value = MagicMock(
        template_code="ohada_v1", template_title="OHADA Balance Sheet"
    )

    service = OhadaBalanceSheetService(
        unit_of_work_factory=_fake_uow,
        ohada_balance_sheet_repository_factory=lambda session: repo,
        balance_sheet_template_service=template_svc,
        ohada_period_result_service=period_result_svc,
    )
    return service


def _build_ias_service(
    bs_rows: list[IasBalanceSheetAccountRow],
    ytd_profit_loss: Decimal,
) -> IasBalanceSheetService:
    repo = MagicMock(spec=IasBalanceSheetRepository)
    repo.list_balance_snapshot.return_value = bs_rows
    repo.sum_ytd_profit_loss.return_value = ytd_profit_loss

    template_svc = MagicMock(spec=BalanceSheetTemplateService)
    template_svc.get_template.return_value = MagicMock(
        template_code="ias_v1", template_title="IAS/IFRS Balance Sheet"
    )

    service = IasBalanceSheetService(
        unit_of_work_factory=_fake_uow,
        ias_balance_sheet_repository_factory=lambda session: repo,
        balance_sheet_template_service=template_svc,
    )
    return service


def _filter() -> ReportingFilterDTO:
    return ReportingFilterDTO(
        company_id=_COMPANY_ID,
        date_from=None,
        date_to=_DATE,
        posted_only=True,
    )


# ---------------------------------------------------------------------------
# Scenario data builders
# ---------------------------------------------------------------------------

def _ohada_interim_profit_rows() -> list[OhadaBalanceSheetAccountRow]:
    """BS accounts: bank=1000 asset, supplier=400 liability, capital=500 equity.
    No closing-result account (prefix 13) present yet. P&L derived = +100 (profit).
    """
    return [
        _make_ohada_bs_account(1, "1011", "Share capital", Decimal("0"), Decimal("500"), "credit"),
        _make_ohada_bs_account(2, "4011", "Supplier A", Decimal("0"), Decimal("400"), "credit"),
        _make_ohada_bs_account(3, "5211", "Bank account", Decimal("1000"), Decimal("0"), "debit"),
    ]


def _ohada_postclosing_rows() -> list[OhadaBalanceSheetAccountRow]:
    """After closing: account 131 carries the result. P&L zeroed."""
    return [
        _make_ohada_bs_account(1, "1011", "Share capital", Decimal("0"), Decimal("500"), "credit"),
        _make_ohada_bs_account(4, "131", "Net result of the period", Decimal("0"), Decimal("100"), "credit"),
        _make_ohada_bs_account(2, "4011", "Supplier A", Decimal("0"), Decimal("400"), "credit"),
        _make_ohada_bs_account(3, "5211", "Bank account", Decimal("1000"), Decimal("0"), "debit"),
    ]


def _ohada_interim_loss_rows() -> list[OhadaBalanceSheetAccountRow]:
    """BS accounts: bank=800, supplier=400, capital=500. P&L derived = -100 (loss)."""
    return [
        _make_ohada_bs_account(1, "1011", "Share capital", Decimal("0"), Decimal("500"), "credit"),
        _make_ohada_bs_account(2, "4011", "Supplier A", Decimal("0"), Decimal("400"), "credit"),
        _make_ohada_bs_account(3, "5211", "Bank account", Decimal("800"), Decimal("0"), "debit"),
    ]


def _ias_interim_profit_rows() -> list[IasBalanceSheetAccountRow]:
    """IAS-style: PPE=600 asset, bank=400 asset, supplier=400 liability, capital=500 equity."""
    return [
        _make_ias_bs_account(1, "1011", "Share capital", Decimal("0"), Decimal("500"), "credit", "EQUITY"),
        _make_ias_bs_account(2, "4011", "Supplier A", Decimal("0"), Decimal("400"), "credit", "LIABILITY"),
        _make_ias_bs_account(3, "5211", "Bank account", Decimal("400"), Decimal("0"), "debit", "ASSET"),
        _make_ias_bs_account(5, "2311", "Buildings", Decimal("600"), Decimal("0"), "debit", "ASSET"),
    ]


def _ias_postclosing_rows() -> list[IasBalanceSheetAccountRow]:
    """IAS after closing: account 12 carries result. P&L zeroed."""
    return [
        _make_ias_bs_account(1, "1011", "Share capital", Decimal("0"), Decimal("500"), "credit", "EQUITY"),
        _make_ias_bs_account(4, "12", "Net result", Decimal("0"), Decimal("100"), "credit", "EQUITY"),
        _make_ias_bs_account(2, "4011", "Supplier A", Decimal("0"), Decimal("400"), "credit", "LIABILITY"),
        _make_ias_bs_account(3, "5211", "Bank account", Decimal("400"), Decimal("0"), "debit", "ASSET"),
        _make_ias_bs_account(5, "2311", "Buildings", Decimal("600"), Decimal("0"), "debit", "ASSET"),
    ]


def _ias_interim_loss_rows() -> list[IasBalanceSheetAccountRow]:
    """IAS loss: bank=300, buildings=600, supplier=400, capital=500. P&L = -100 loss."""
    return [
        _make_ias_bs_account(1, "1011", "Share capital", Decimal("0"), Decimal("500"), "credit", "EQUITY"),
        _make_ias_bs_account(2, "4011", "Supplier A", Decimal("0"), Decimal("400"), "credit", "LIABILITY"),
        _make_ias_bs_account(3, "5211", "Bank account", Decimal("300"), Decimal("100"), "debit", "ASSET"),
        _make_ias_bs_account(5, "2311", "Buildings", Decimal("600"), Decimal("0"), "debit", "ASSET"),
    ]


# ---------------------------------------------------------------------------
# Test 1: OHADA interim profit — should balance
# ---------------------------------------------------------------------------
print("\n=== 1. OHADA interim with YTD profit (no closing entry) ===")

svc = _build_ohada_service(_ohada_interim_profit_rows(), ytd_profit_loss=Decimal("100.00"))
report = svc.get_statement(_filter())

check("total_assets == 1000", report.total_assets == Decimal("1000.00"), f"got {report.total_assets}")
# Expected: capital 500 + supplier 400 + derived CI 100 = 1000
check(
    "total_liabilities_and_equity == 1000",
    report.total_liabilities_and_equity == Decimal("1000.00"),
    f"got {report.total_liabilities_and_equity}",
)
check("balance_difference == 0", report.balance_difference == _ZERO, f"got {report.balance_difference}")

# Verify CI line has the derived amount
ci_line = next((l for l in report.liability_lines if l.code == "CI"), None)
check("CI line found", ci_line is not None)
if ci_line:
    check("CI net_amount == 100", ci_line.net_amount == Decimal("100.00"), f"got {ci_line.net_amount}")


# ---------------------------------------------------------------------------
# Test 2: IAS interim profit — should balance
# ---------------------------------------------------------------------------
print("\n=== 2. IAS interim with YTD profit (no closing entry) ===")

ias_svc = _build_ias_service(_ias_interim_profit_rows(), ytd_profit_loss=Decimal("100.00"))
ias_report = ias_svc.get_statement(_filter())

check(
    "total_assets == 1000",
    ias_report.total_assets == Decimal("1000.00"),
    f"got {ias_report.total_assets}",
)
# Expected: capital 500 + supplier 400 + derived CURRENT_YEAR_RESULT 100 = 1000
check(
    "total_equity_and_liabilities == 1000",
    ias_report.total_equity_and_liabilities == Decimal("1000.00"),
    f"got {ias_report.total_equity_and_liabilities}",
)
check("balance_difference == 0", ias_report.balance_difference == _ZERO, f"got {ias_report.balance_difference}")

cyr_line = next((l for l in ias_report.lines if l.code == "CURRENT_YEAR_RESULT"), None)
check("CURRENT_YEAR_RESULT line found", cyr_line is not None)
if cyr_line:
    check("CURRENT_YEAR_RESULT amount == 100", cyr_line.amount == Decimal("100.00"), f"got {cyr_line.amount}")


# ---------------------------------------------------------------------------
# Test 3: OHADA post-closing — no double count
# ---------------------------------------------------------------------------
print("\n=== 3. OHADA post-closing (no double count) ===")

svc2 = _build_ohada_service(_ohada_postclosing_rows(), ytd_profit_loss=_ZERO)
report2 = svc2.get_statement(_filter())

check("total_assets == 1000", report2.total_assets == Decimal("1000.00"), f"got {report2.total_assets}")
check(
    "total_liabilities_and_equity == 1000",
    report2.total_liabilities_and_equity == Decimal("1000.00"),
    f"got {report2.total_liabilities_and_equity}",
)
check("balance_difference == 0", report2.balance_difference == _ZERO, f"got {report2.balance_difference}")

ci2 = next((l for l in report2.liability_lines if l.code == "CI"), None)
if ci2:
    check("CI net_amount == 100 (from account 131 only)", ci2.net_amount == Decimal("100.00"), f"got {ci2.net_amount}")


# ---------------------------------------------------------------------------
# Test 4: IAS post-closing — no double count
# ---------------------------------------------------------------------------
print("\n=== 4. IAS post-closing (no double count) ===")

ias_svc2 = _build_ias_service(_ias_postclosing_rows(), ytd_profit_loss=_ZERO)
ias_report2 = ias_svc2.get_statement(_filter())

check(
    "total_assets == 1000",
    ias_report2.total_assets == Decimal("1000.00"),
    f"got {ias_report2.total_assets}",
)
check(
    "total_equity_and_liabilities == 1000",
    ias_report2.total_equity_and_liabilities == Decimal("1000.00"),
    f"got {ias_report2.total_equity_and_liabilities}",
)
check("balance_difference == 0", ias_report2.balance_difference == _ZERO, f"got {ias_report2.balance_difference}")


# ---------------------------------------------------------------------------
# Test 5: OHADA interim loss — should balance
# ---------------------------------------------------------------------------
print("\n=== 5. OHADA interim with YTD loss ===")

svc3 = _build_ohada_service(_ohada_interim_loss_rows(), ytd_profit_loss=Decimal("-100.00"))
report3 = svc3.get_statement(_filter())

check("total_assets == 800", report3.total_assets == Decimal("800.00"), f"got {report3.total_assets}")
# Expected: capital 500 + supplier 400 + derived CI -100 = 800
check(
    "total_liabilities_and_equity == 800",
    report3.total_liabilities_and_equity == Decimal("800.00"),
    f"got {report3.total_liabilities_and_equity}",
)
check("balance_difference == 0", report3.balance_difference == _ZERO, f"got {report3.balance_difference}")

ci3 = next((l for l in report3.liability_lines if l.code == "CI"), None)
if ci3:
    check("CI net_amount == -100 (loss)", ci3.net_amount == Decimal("-100.00"), f"got {ci3.net_amount}")


# ---------------------------------------------------------------------------
# Test 6: IAS interim loss — should balance
# ---------------------------------------------------------------------------
print("\n=== 6. IAS interim with YTD loss ===")

ias_svc3 = _build_ias_service(_ias_interim_loss_rows(), ytd_profit_loss=Decimal("-100.00"))
ias_report3 = ias_svc3.get_statement(_filter())

check(
    "total_assets == 800",
    ias_report3.total_assets == Decimal("800.00"),
    f"got {ias_report3.total_assets}",
)
# Expected: capital 500 + supplier 400 + CURRENT_YEAR_RESULT -100 = 800
check(
    "total_equity_and_liabilities == 800",
    ias_report3.total_equity_and_liabilities == Decimal("800.00"),
    f"got {ias_report3.total_equity_and_liabilities}",
)
check("balance_difference == 0", ias_report3.balance_difference == _ZERO, f"got {ias_report3.balance_difference}")


# ---------------------------------------------------------------------------
# Test 7: Zero P&L — no effect
# ---------------------------------------------------------------------------
print("\n=== 7. Zero P&L — no injection effect ===")

svc4 = _build_ohada_service(_ohada_interim_profit_rows(), ytd_profit_loss=_ZERO)
report4 = svc4.get_statement(_filter())

# Without P&L derivation and no account 13: equity = 500, liab = 400 → 900 < 1000 assets
check(
    "balance_difference == 100 (as expected without P&L)",
    report4.balance_difference == Decimal("100.00"),
    f"got {report4.balance_difference}",
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"RESULTS: {passed} passed, {failed} failed")
if failed > 0:
    print("VALIDATION FAILED")
    sys.exit(1)
else:
    print("ALL INTERIM BALANCE SHEET TESTS PASSED")
    sys.exit(0)
