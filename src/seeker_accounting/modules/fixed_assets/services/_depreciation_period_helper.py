from __future__ import annotations

from datetime import date


def months_elapsed(from_date: date, to_date: date) -> int:
    """Return the number of complete months elapsed from from_date to to_date (inclusive month count).

    Month 1 = the calendar month of from_date.
    Month 2 = the following calendar month, etc.
    Returns 0 if to_date is before from_date.
    """
    if to_date < from_date:
        return 0
    years_diff = to_date.year - from_date.year
    months_diff = to_date.month - from_date.month
    total = years_diff * 12 + months_diff + 1  # +1 because month 1 = same month as capitalization
    return max(0, total)
