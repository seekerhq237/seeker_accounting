from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def quantize_money(value: Decimal | float | int | str) -> Decimal:
    amount = Decimal(str(value))
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_money(value: Decimal | float | int | str, currency_code: str = "XAF") -> str:
    amount = quantize_money(value)
    return f"{currency_code} {amount:,.2f}"

