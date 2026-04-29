"""Catalog of valid financial account types and labels."""
from __future__ import annotations

# Mirrors `_ALLOWED_FINANCIAL_ACCOUNT_TYPE_CODES` in financial_account_service.
ACCOUNT_TYPE_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("bank", "Bank account",
     "Operating or savings account at a bank. Bank name and account number are recommended."),
    ("cash", "Cash on hand",
     "Physical cash float held by the business (till, safe, etc.)."),
    ("petty_cash", "Petty cash",
     "Small float for incidental expenses, often replenished from a bank account."),
)
