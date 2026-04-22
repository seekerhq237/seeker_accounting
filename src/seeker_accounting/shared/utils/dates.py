from __future__ import annotations

from datetime import date, datetime


def format_date(value: date | datetime | None, format_string: str = "%d %b %Y") -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime(format_string)
    return value.strftime(format_string)


def format_month_period(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%b %Y")

