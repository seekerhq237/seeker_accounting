"""Validate deferred items from Phase 3 (Account Ledger, Item Movements) and Phase 4
(Cash trend chart, MoM deltas)."""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


def _banner(msg: str) -> None:
    print(f"\n=== {msg} ===")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. DTO construction
    _banner("DTO CONSTRUCTION")
    from seeker_accounting.modules.dashboard.dto.dashboard_dto import (
        DashboardCashLiquidityDTO,
        DashboardCashTrendPointDTO,
        DashboardDataDTO,
        DashboardKpiDeltaDTO,
        DashboardKpiDTO,
    )

    trend_point = DashboardCashTrendPointDTO(
        as_of=date(2025, 1, 10), inflow=Decimal("12500"), outflow=Decimal("3400")
    )
    liquidity = DashboardCashLiquidityDTO(trend_points=(trend_point,))
    deltas = DashboardKpiDeltaDTO(revenue_delta_pct=Decimal("12.5"), expenses_delta_pct=Decimal("-3.1"))
    data = DashboardDataDTO(
        kpis=DashboardKpiDTO(),
        kpi_deltas=deltas,
        cash_liquidity=liquidity,
    )
    assert data.kpi_deltas.revenue_delta_pct == Decimal("12.5")
    assert data.cash_liquidity.trend_points[0].inflow == Decimal("12500")
    print("  DTO round-trip OK")

    # 2. QSS build with new trend legend tokens
    _banner("QSS BUILD")
    from seeker_accounting.shared.ui.styles.qss_builder import build_stylesheet
    from seeker_accounting.shared.ui.styles.palette import LIGHT_PALETTE, DARK_PALETTE
    from seeker_accounting.shared.ui.styles.tokens import ThemeTokens

    tokens = ThemeTokens()
    for name, palette in (("light", LIGHT_PALETTE), ("dark", DARK_PALETTE)):
        qss = build_stylesheet(palette, tokens)
        assert "DashboardTrendLegendInflow" in qss, f"{name} missing trend legend"
        assert "DashboardTrendLegendOutflow" in qss
        print(f"  {name}: {len(qss):,} chars, trend legend present")

    # 3. Import & instantiate modified widgets
    _banner("WIDGET INSTANTIATION")

    from seeker_accounting.modules.dashboard.ui.dashboard_page import TrendChart
    chart = TrendChart()
    chart.set_points((trend_point,))
    chart.resize(400, 140)
    chart.show()
    app.processEvents()
    print("  TrendChart OK")

    # 4. Import the detail pages (no instantiation — requires full service registry)
    _banner("IMPORT CHAIN")
    from seeker_accounting.modules.accounting.chart_of_accounts.ui import account_detail_page  # noqa: F401
    from seeker_accounting.modules.inventory.ui import item_detail_page  # noqa: F401
    print("  AccountDetailPage import OK")
    print("  ItemDetailPage import OK")

    _banner("DEFERRED ITEMS VALIDATION: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
